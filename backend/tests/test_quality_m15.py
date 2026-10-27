"""Test M1.5 sesuai docs/scenarios/M1.5.md (data sintetis, pola mainan)."""
from fractions import Fraction as F

import pytest

from backend.quality.aggregate import (
    macro_recall, pooled_counts, quality_metrics, top_k, validate_k,
)
from backend.quality.boundaries import sent
from backend.quality.types import ChunkSpan as C, QualityDoc

PATTERNS = [r"Pasal \d+[A-Z]?", r"ayat \(\d\)", r"UU \d+/\d{4}"]
ABBR = {"No", "dst", "dll"}

DA = ("Pasal 1\n(1) Perseroan wajib berbadan hukum. (2) Modal dasar dibagi atas saham.\n"
      "Pasal 2\n(1) Lihat Pasal 1 ayat (2) dan UU 40/2007.")
SA = frozenset({0, 7, 8, 43, 44, 78, 79, 86, 87, 129})
DB = "Pasal 3 No. 7 memuat 1.000 saham. Pasal 4 selesai."
SB = frozenset({0, 50})
DC = "Aaa bbb ccc."
SC = frozenset({0, 12})
DD = "\U0001F600 Pasal 153A dan Pasal 12 berlaku.\nAda dst. Lalu ANo. Lalu dll.\nSelesai"
SD = frozenset({0, 71})


def doc(text, S, *spans, hdr=""):
    return QualityDoc(text, tuple(C(s, e, hdr) for s, e in spans), S)


def metrics(*docs, k=2, rec=()):
    return quality_metrics("s", list(docs), k, rec, PATTERNS, ABBR)


def check(m, ep, bc):
    for got, exp in ((m.entity_preservation, ep), (m.boundary_coherence, bc)):
        if exp is None:
            assert got is None
        else:
            assert got == pytest.approx(float(exp), abs=1e-9)


def test_fixture_lengths():
    assert (len(DA), len(DB), len(DC), len(DD)) == (129, 50, 12, 71)
    assert len(DD.encode("utf-16-le")) // 2 == 72


# ---------- S1-S8 ----------
def test_S1_satu_potongan_utuh_penyebut_nol_null():
    m = metrics(doc(DA, SA, (0, 129)))
    check(m, 1.0, None)
    assert m.counts.bnd_den == 0 and m.counts.entity_den == 5


def test_S2_batas_pada_batas_struktur():
    check(metrics(doc(DA, SA, (0, 79), (79, 129))), 1.0, 1.0)


def test_S3_nomor_pasal_terbelah():
    m = metrics(doc(DA, SA, (0, 100), (100, 129)))
    check(m, F(4, 5), 0.0)
    assert (m.counts.bnd_num, m.counts.bnd_den) == (0, 1)


def test_S3b_entitas_pas_di_tepi():
    check(metrics(doc(DA, SA, (0, 104), (104, 129))), 1.0, 0.0)


def test_S4_entitas_di_overlap_tidak_digandakan():
    m = metrics(doc(DA, SA, (0, 110), (90, 129)))
    check(m, 1.0, 0.0)
    assert (m.counts.entity_num, m.counts.entity_den) == (5, 5)


def test_S4b_terbelah_di_c1_utuh_di_c2():
    check(metrics(doc(DA, SA, (0, 100), (90, 129))), 1.0, 0.0)


def test_S5_entitas_bertumpuk_terpisah():
    m = metrics(doc(DA, SA, (0, 105), (105, 129)))
    check(m, 1.0, 0.0)
    assert m.counts.entity_den == 5


def test_S6_entitas_di_celah():
    check(metrics(doc(DA, SA, (0, 79), (87, 129))), F(4, 5), 1.0)


def test_S7_tabel_ok_per_posisi():
    ch = [(0, 7), (7, 40), (40, 42), (42, 43), (43, 44), (44, 45), (45, 78),
          (78, 100), (100, 104), (104, 128), (128, 129)]
    m = metrics(doc(DA, SA, *ch))
    check(m, F(4, 5), F(4, 10))
    assert (m.counts.bnd_num, m.counts.bnd_den) == (4, 10)
    ok = {b: (b in SA or sent(DA, b, ABBR)) for _, b in ch[:-1]}
    assert ok == {7: True, 40: False, 42: False, 43: True, 44: True, 45: False,
                  78: True, 100: False, 104: False, 128: False}


def test_S8_akhir_kalimat_berdiri_sendiri():
    m = metrics(doc(DB, SB, (0, 6), (6, 11), (11, 23), (23, 33), (33, 50)))
    check(m, F(1, 2), F(1, 4))


# ---------- S9-S11 ----------
def test_S9_pooled_bukan_macro():
    m = metrics(doc(DA, SA, (0, 100), (100, 129)), doc(DB, SB, (0, 11), (11, 33), (33, 50)))
    check(m, F(6, 7), F(1, 3))
    c = m.counts
    assert (c.entity_num, c.entity_den, c.bnd_num, c.bnd_den) == (6, 7, 1, 3)


def test_S10_dokumen_nol_tidak_mengencerkan_dan_semua_nol_null():
    check(metrics(doc(DA, SA, (0, 100), (100, 129)), doc(DC, SC, (0, 12))), 0.8, 0.0)
    check(metrics(doc(DC, SC, (0, 12))), None, None)


def test_S11_metrik_atas_seluruh_potongan_bukan_per_butir():
    d = doc(DA, SA, (0, 100), (100, 129))
    a = metrics(d)
    b = metrics(d, rec=[F(1), F(0), None])
    c = metrics(d, rec=[None])
    for m in (a, b, c):
        check(m, 0.8, 0.0)
    assert c.recall_at_k is None


# ---------- Recall@K (helper test: definisi skenario) ----------
def part_in_chunk(g, c):
    return c[0] <= g[0] and g[1] <= c[1]


def recall_item(parts, ranking, k):
    if not parts:
        return None
    sel = top_k(ranking, k)
    return F(sum(1 for g in parts if any(part_in_chunk(g, c) for c in sel)), len(parts))


G1, G2, G3 = (8, 43), (44, 78), (97, 113)
SS = {"sA": (0, 43), "sB": (44, 78), "sC": (79, 129)}
FF = {"f1": (0, 50), "f2": (50, 100), "f3": (100, 129)}
ITEMS = [[G1, G2], [G3], []]
RANK_S = [["sB", "sA", "sC"], ["sA", "sB", "sC"], ["sA", "sB", "sC"]]
RANK_F = [["f1", "f2", "f3"], ["f3", "f1", "f2"], ["f1", "f2", "f3"]]


def agg(chs, ranks, k, items=ITEMS):
    vals = [recall_item(p, [chs[i] for i in r], k) for p, r in zip(items, ranks)]
    return macro_recall(vals)


def test_S12_recall_struktur_vs_ukuran_tetap():
    assert agg(SS, RANK_S, 2) == F(1, 2)
    assert agg(FF, RANK_F, 2) == F(1, 4)


def test_S13_batas_k():
    q2 = [[G3]]
    r = [["sA", "sB", "sC"]]
    assert agg(SS, r, 2, q2) == 0
    assert agg(SS, r, 3, q2) == 1
    assert agg(SS, r, 10, q2) == 1
    with pytest.raises(ValueError):
        top_k(r[0], -1)
    with pytest.raises(ValueError):
        validate_k(1.5)
    with pytest.raises(ValueError):
        validate_k(True)


@pytest.mark.pending_operator
def test_S13_k0_cabang_K0a_menunggu_I31():
    """Menunggu I-31: K0-a (Recall@0 = 0,0)."""
    assert top_k(["a", "b"], 0) == []
    assert agg(SS, RANK_S, 0) == 0
    assert agg(FF, RANK_F, 0) == 0
    assert agg(SS, [["sA", "sB", "sC"]], 0, [[G3]]) == 0


def test_S14_overlap_menyelamatkan_recall_tanpa_anggaran():
    ff = {"f1": (0, 50), "f2": (40, 100), "f3": (90, 129)}
    ranks = [["f1", "f2", "f3"], ["f3", "f1", "f2"]]
    assert agg(ff, ranks, 2, ITEMS[:2]) == 1


# ---------- S15, S16 ----------
def test_S15_dua_potongan_end_sama_per_potongan():
    m = metrics(doc(DA, SA, (0, 43), (20, 43), (43, 129)))
    check(m, 1.0, 1.0)
    assert (m.counts.bnd_num, m.counts.bnd_den) == (2, 2)


def test_S16_urutan_dan_header_tidak_mengubah():
    for spans, hdr in [(((0, 100), (100, 129)), ""),
                       (((100, 129), (0, 100)), ""),
                       (((0, 100), (100, 129)), "Pasal 1 ayat (2)"),
                       (((100, 129), (0, 100)), "Pasal 2 UU 40/2007")]:
        m = metrics(doc(DA, SA, *spans, hdr=hdr))
        check(m, 0.8, 0.0)
        assert m.counts.entity_den == 5
    check(metrics(doc(DA, SA, (79, 129), (0, 43), (44, 78))), 1.0, 1.0)
    m = metrics(doc(DA, SA, (0, 79), (100, 129), (79, 100)))
    check(m, 0.8, 0.5)
    assert (m.counts.bnd_num, m.counts.bnd_den) == (1, 2)


# ---------- S17 ----------
def panel(which, k):
    if which == "struktur":
        d = doc(DA, SA, (0, 43), (44, 78), (79, 129))
        rec = [recall_item(p, [SS[i] for i in r], k) for p, r in zip(ITEMS, RANK_S)]
        return quality_metrics("structure_handwritten", [d], k, rec, PATTERNS, ABBR)
    d = doc(DA, SA, (0, 50), (50, 100), (100, 129))
    rec = [recall_item(p, [FF[i] for i in r], k) for p, r in zip(ITEMS, RANK_F)]
    return quality_metrics("fixed_size", [d], k, rec, PATTERNS, ABBR)


def test_S17_lima_panggilan_berurutan_tanpa_keadaan_bocor():
    def tup(m):
        return (m.entity_preservation, m.boundary_coherence, m.recall_at_k, m.k)
    r1 = panel("struktur", 2)
    r2 = panel("tetap", 2)
    r3 = panel("struktur", 2)
    r4 = panel("struktur", 3)
    r5 = panel("tetap", 3)
    assert tup(r1) == (1.0, 1.0, 0.5, 2)
    assert tup(r2) == (0.8, 0.0, 0.25, 2)
    assert tup(r3) == tup(r1)
    assert tup(r4) == (1.0, 1.0, 1.0, 3)
    assert tup(r5) == (0.8, 0.0, 0.25, 3)
    assert r1.setting_id != r2.setting_id
    assert (r2.counts.bnd_num, r2.counts.bnd_den) == (0, 2)


# ---------- S18-S20 ----------
def test_S18_newline_singkatan_batas_kata():
    m = metrics(doc(DD, SD, (0, 34), (34, 43), (43, 53), (53, 63), (63, 71)))
    check(m, 1.0, 0.5)
    assert [sent(DD, b, ABBR) for b in (34, 43, 53, 63)] == [True, False, True, False]


@pytest.mark.parametrize("spans,ep,bc", [
    (((0, 11), (11, 71)), 0.5, 0.0),
    (((0, 24), (24, 71)), 0.5, 0.0),
    (((0, 12), (12, 71)), 1.0, 0.0),
])
def test_S19_pasal_berhuruf_multidigit_non_bmp(spans, ep, bc):
    check(metrics(doc(DD, SD, *spans)), ep, bc)


def test_S20_sent_langsung_akhir_dokumen_dan_tepi():
    assert sent(DB, 50, ABBR) is True
    assert sent(DC, 12, ABBR) is True
    assert sent(DD, 71, ABBR) is False
    assert sent(DB, 33, ABBR) is True
    assert sent(DB, 11, ABBR) is False
    assert sent(DB, 23, ABBR) is False
    assert sent("Lihat No 1. Baru", 11, ABBR) is True
    assert sent(". Aaa", 1, ABBR) is True
    assert sent("Aaa.. Bbb", 5, ABBR) is True
    assert sent("Aaa.. Bbb", 4, ABBR) is False


# ---------- S21 ----------
def test_S21_agregat_recall_tanpa_butir_bergold():
    assert agg(SS, RANK_S[2:], 2, ITEMS[2:]) is None
    assert macro_recall([]) is None
    assert agg(SS, RANK_S, 2) == F(1, 2)
    m = metrics(doc(DA, SA, (0, 100), (100, 129)), rec=[])
    assert m.recall_at_k is None
