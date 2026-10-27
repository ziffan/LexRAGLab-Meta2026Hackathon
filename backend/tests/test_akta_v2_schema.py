"""Skema A akta v2 (H-088, W40): berkas koreksi varian (ii), cakupan potongan lima akta, alamat non-Pasal (G-5),
peta alamat akta untuk label konteks C (H-070) dan verifier V5-strict (H-067), dan UU PT tidak berubah.
Berkas koreksi dan lima akta dibaca saja; tidak ada SchemaRecord yang disimpan."""

from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace

import pytest

from backend import config
from backend.answer.context import entry_labels, unit_label
from backend.chunking import chunk_document, schema_address_fn, schema_address_map
from backend.corpus import load_corpus
from backend.schema_a import SchemaStore, load_correction_file, parent_samples, validate_body
from backend.verifier import (ChunkSpan, load_verifier_config, units_from_address_map, verify_citation)

from ._chunk_util import ToyWs

CORR = config.REPO_ROOT / "_kerja" / "orkestrasi" / "skemaA-akta-v2-koreksi.json"
DEEDS = [f"akta-0{i}" for i in range(1, 6)]
N_PASAL = {"akta-01": 14, "akta-02": 17, "akta-03": 20, "akta-04": 22, "akta-05": 25}
NON_PASAL = ["Kepala Akta", "Komparisi", "Keterangan Pendiri", "Penutup Akta"]


CORR_B = config.REPO_ROOT / "_kerja" / "orkestrasi" / "skemaA-akta-v2-koreksi-b.json"
_COMMON = (r"^(?:ANGGARAN DASAR\s+)?Pasal\s+\d+\s*$|^(?P<kepala_akta>AKTA [A-Z][A-Z ]*)$|")
_TAIL = r"|^(?P<keterangan_pendiri>KETERANGAN PENDIRI)\b|^(?P<penutup_akta>PENUTUP)\s*$"
# Pola level 1 disalin ke test (berkas di _kerja/ tidak di-commit): (a) komparisi mulai di 'Menghadap'; (b) di butir penghadap pertama.
PATTERNS = {
    "a": _COMMON + r"^(?P<komparisi>(?:Menghadap kepada|Berhadapan dengan) saya)\b" + _TAIL,
    "b": _COMMON + r"^(?P<komparisi>1\.)(?=\s+(?:Tuan|Nyonya|Nona)\s+[A-Z]{2,}\s)" + _TAIL,
}
FILES = {"a": CORR, "b": CORR_B}


@pytest.fixture(scope="module", params=["a", "b"])
def variant(request):
    return request.param


@pytest.fixture(scope="module")
def corr(variant):
    c = load_correction_file(FILES[variant]) if FILES[variant].exists() else load_correction_file(CORR)
    c["schema"] = json.loads(json.dumps(c["schema"]))
    c["schema"]["levels"][0]["marker_pattern"] = PATTERNS[variant]
    if FILES[variant].exists():  # berkas ada: pola tertanam harus sama dengan berkas
        assert load_correction_file(FILES[variant])["schema"]["levels"][0]["marker_pattern"] == PATTERNS[variant]
    if variant == "b":
        c["schema"]["levels"][0]["examples"] = [e for e in c["schema"]["levels"][0]["examples"] if not e.startswith("Menghadap")] + ["1. Tuan WIRASENA KARTAPRADJA LUBIS"]
    return c


@pytest.fixture(scope="module")
def rec(corr):
    return {"family": "akta", "schema_version": 2, "source": "operator", "parent_version": 1, "body": corr["schema"]}


@pytest.fixture(scope="module")
def docs():
    return {i: load_corpus(i) for i in DEEDS}


def chunks_of(doc, rec):
    return sorted(chunk_document(doc, {"chunker": "structure_schema"}, tokenizer=ToyWs(), schema_record=rec),
                  key=lambda c: (c.start, c.end))


def test_correction_file_valid_against_parent_samples(corr):
    parent = SchemaStore(config.REPO_ROOT / "runs").get("akta", 1)
    samples = parent_samples(parent, load_corpus)
    errs, val = validate_body(corr["schema"], family="akta", samples=samples)
    assert errs == [] and val and all(v["matched"] for v in val)
    assert corr["parent_version"] == 1 and corr["schema"]["default_chunk_level"] == 1
    assert [lv["name"] for lv in corr["schema"]["levels"]] == ["pasal", "ayat", "huruf"]


@pytest.mark.parametrize("doc_id", DEEDS)
def test_five_deeds_cover_text_exactly_with_g5_addresses(doc_id, docs, rec, variant):
    d = docs[doc_id]
    ch = chunks_of(d, rec)
    t = d.text
    pre = d.metadata["address_prefix"]
    # cakupan: semua karakter bukan-spasi tepat satu kali; tidak ada tumpang tindih; awal akta ada di potongan pertama (G-37)
    cov = [0] * len(t)
    for c in ch:
        for k in range(c.start, c.end):
            cov[k] += 1
    assert not [k for k, ch_ in enumerate(t) if not ch_.isspace() and cov[k] == 0]
    assert max(cov) == 1
    assert ch[0].start == len(t) - len(t.lstrip()) and t[ch[0].start:].startswith("AKTA ")
    assert all(a.end <= b.start for a, b in zip(ch, ch[1:]))
    # urutan dan alamat persis (G-5)
    n = N_PASAL[doc_id]
    want = [f"{pre} › Kepala Akta", f"{pre} › Komparisi", *[f"{pre} › Pasal {i}" for i in range(1, n + 1)],
            f"{pre} › Keterangan Pendiri", f"{pre} › Penutup Akta"]
    assert [c.address for c in ch] == want
    assert all(c.warnings == [] for c in ch)
    # isi batas (G-2, G-3, G-4)
    by = {c.address.split(" › ", 1)[1]: t[c.start:c.end] for c in ch}
    assert by["Kepala Akta"].startswith("AKTA ") and "Nomor" in by["Kepala Akta"] and "Pada hari ini" in by["Kepala Akta"]
    assert not re.search(r"^1\. ", by["Kepala Akta"], re.M)
    k = by["Komparisi"]
    if variant == "a":  # G-4 harfiah: komparisi mulai di 'Menghadap kepada saya'
        assert "Menghadap" not in by["Kepala Akta"] and k.startswith("Menghadap kepada saya")
    else:  # (b): klausa Notaris di kepala; komparisi mulai di butir penghadap pertama
        assert re.search(r"Menghadap kepada saya, [A-Z ]+, .*Notaris berkedudukan di", by["Kepala Akta"])
        assert k.startswith("1. ") and "Menghadap" not in k
    assert re.search(r"Para penghadap (dikenal|diperkenalkan)", k)
    assert "ANGGARAN DASAR" not in k and "Pasal 1" not in k
    assert by["Pasal 1"].startswith("ANGGARAN DASAR") and re.match(r"ANGGARAN DASAR\s+Pasal 1\s", by["Pasal 1"])
    assert by[f"Pasal {n}"].count("KETERANGAN PENDIRI") == 0 and "PENUTUP" not in by[f"Pasal {n}"]
    assert by["Keterangan Pendiri"].startswith("KETERANGAN PENDIRI") and "PENUTUP" not in by["Keterangan Pendiri"]
    assert by["Penutup Akta"].startswith("PENUTUP") and ch[-1].end == len(t.rstrip())
    assert [c.section for c in ch] == ["batang_tubuh"] * len(ch)


def test_non_pasal_address_levels_and_ids_distinct(docs, rec):
    ch = chunks_of(docs["akta-01"], rec)
    assert len({c.chunk_id for c in ch}) == len(ch)
    k = next(c for c in ch if c.address.endswith("Komparisi"))
    assert k.address_levels[-1] == {"level": "pasal", "label": "Komparisi"}  # level 'pasal' memuat label non-Pasal


def test_synthetic_marker_variants_and_labels(rec, variant):
    """Kasus sintetis kecil: 'Berhadapan dengan saya', tanpa judul ANGGARAN DASAR, Pasal bernomor ayat/huruf, tanpa Keterangan
    Pendiri. Label berasal dari nama grup, bukan dari nama akta tertentu."""
    text = ("AKTA PENDIRIAN\nPT X\n\nNomor : 1\n\nBerhadapan dengan saya, N, Notaris di Y:\n\n1. Tuan AAA BBB, lahir.\n\n"
            "Pasal 1\n\n(1) Satu.\n(2) Dua:\na. alfa;\nb. beta.\n\nPasal 2\n\nTeks dua.\n\nPENUTUP\n\nDemikian.\n")
    doc = SimpleNamespace(doc_id="s-1", family="akta", text=text, clean_sha256="0" * 64, metadata={"address_prefix": "Akta S1"},
                          sections=[{"section": "batang_tubuh", "start": 0, "end": len(text)}])
    ch = chunk_document(doc, {"chunker": "structure_schema"}, tokenizer=ToyWs(), schema_record=rec)
    ch = sorted(ch, key=lambda c: c.start)
    assert [c.address for c in ch] == ["Akta S1 › Kepala Akta", "Akta S1 › Komparisi", "Akta S1 › Pasal 1", "Akta S1 › Pasal 2",
                                       "Akta S1 › Penutup Akta"]
    if variant == "a":
        assert text[ch[1].start:].startswith("Berhadapan dengan saya") and text[ch[0].start:ch[0].end].endswith("Nomor : 1")
    else:
        assert text[ch[1].start:].startswith("1. Tuan AAA") and text[ch[0].start:ch[0].end].endswith("Notaris di Y:")
    assert text[ch[-1].start:ch[-1].end].endswith("Demikian.")
    fn = schema_address_fn(doc, rec)
    p = text.index("b. beta")
    assert fn(p, p + 7, "batang_tubuh")[0] == "Akta S1 › Pasal 1 › ayat (2) › huruf b"  # Pasal tetap H-076
    q = text.index("(2) Dua")
    assert fn(q, q + 7, "batang_tubuh")[0] == "Akta S1 › Pasal 1 › ayat (2)"


def test_address_map_matches_chunk_addresses_and_children(docs, rec):
    d = docs["akta-02"]
    amap = schema_address_map(d, rec)
    ch = chunks_of(d, rec)
    assert [(u.start, u.end, u.address) for u in amap.units] == [(c.start, c.end, c.address) for c in ch]
    units = units_from_address_map(amap, d.text)
    for a in ("Akta 02 › Kepala Akta", "Akta 02 › Komparisi", "Akta 02 › Keterangan Pendiri", "Akta 02 › Penutup Akta",
              "Akta 02 › Pasal 1"):
        assert a in units, a
    assert any(re.fullmatch(r"Akta 02 › Pasal \d+ › ayat \(\d+\)", a) for a in units)
    assert any(a.count(" › ") == 3 and "huruf" in a for a in units)  # Pasal › ayat › huruf tetap sah


def test_v5_strict_accepts_non_pasal_addresses_and_rejects_others(docs, rec):
    d = docs["akta-02"]
    units = units_from_address_map(schema_address_map(d, rec), d.text)
    conf = load_verifier_config()
    for name in NON_PASAL:
        addr = f"Akta 02 › {name}"
        quote = d.text[units[addr].start:units[addr].start + 25]
        r = verify_citation({"alamat": addr, "teks": quote}, units, [ChunkSpan("c", 0, len(d.text))], conf).result
        assert (r.exists, r.faithful) == ("lulus", "lulus"), addr
    for bad in ("Akta 02 › Komparisi 1", "Akta 02 › komparisi", "Akta 02 › Pasal 99", "Akta 02 › Para penghadap", "Komparisi"):
        r = verify_citation({"alamat": bad, "teks": "x"}, units, [], conf).result
        assert r.exists == "gagal", bad


def test_context_labels_for_chunk_spanning_non_pasal_units(docs, rec):
    d = docs["akta-02"]
    amap = schema_address_map(d, rec)
    k = next(u for u in amap.units if u.address.endswith("Komparisi"))
    p1 = next(u for u in amap.units if u.address.endswith("Pasal 1"))
    labs = entry_labels(amap, k.start, p1.end)  # potongan fixed_size yang melintasi komparisi dan Pasal 1
    assert [x[1] for x in labs] == [unit_label("Akta 02 › Komparisi"), unit_label("Akta 02 › Pasal 1")]
    assert labs[0][0] == 0 and labs[1][0] == p1.start - k.start
    assert entry_labels(amap, k.start, k.end) == ()  # satu unit: tanpa label (byte-identik)
    addr, _lv, w = amap.address_for_range(k.start, p1.end, "batang_tubuh", "Akta 02", "Batang Tubuh")
    assert addr == "Akta 02 › Komparisi – Akta 02 › Pasal 1" and w == []


UUPT_V2_SHA = "dbb24bf789e582915607c1e8ecd5913c117065f52f396d46f6ee637faaa7847c"  # hash (start, end, address) sebelum W40


def test_uupt_schema_v2_chunks_and_addresses_unchanged():
    from backend.tokenizer import get_tokenizer
    rec_u = SchemaStore(config.REPO_ROOT / "runs").get("uupt", 2)
    if rec_u is None:
        pytest.skip("runs/schemas/uupt/v2.json absent")
    doc = load_corpus("uupt-40-2007")
    cs = chunk_document(doc, {"chunker": "structure_schema"}, tokenizer=get_tokenizer(), schema_record=rec_u)
    trip = [(c.start, c.end, c.address) for c in cs]
    assert len(trip) == 343
    assert hashlib.sha256(json.dumps(trip, ensure_ascii=False).encode()).hexdigest() == UUPT_V2_SHA
