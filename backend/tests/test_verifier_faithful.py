"""M2.3 uji 2 Faithful (S12-S23, S25, S26, S35-S37, S39 verifier, S40, S41, S18)."""

import copy
import random
import socket
from fractions import Fraction as F

from backend.verifier import VerifierConfigError, fuzzy_match, verify_answer
from backend.verifier.fuzzy import _search_row, search_row_naive

from .verifier_fixtures import AKTA_MAP, OP, P4, UNITS, UUPT_MAP, a, cfg, chunks, verify

A11 = a("Pasal 1", "ayat (1)")
A12 = a("Pasal 1", "ayat (2)")
A31 = a("Pasal 3", "ayat (1)")
A32 = a("Pasal 3", "ayat (2)")
A41 = a("Pasal 4", "ayat (1)")
A71 = a("Pasal 7", "ayat (1)")
A81 = a("Pasal 8", "ayat (1)")
A82 = a("Pasal 8", "ayat (2)")


def fz(addr, teks, conf=OP, **kw):
    r = verify(addr, teks, conf=conf, **kw)
    return r.faithful, r.faithful_score


def test_fuzzy_myers_matches_naive_dp_and_windows_bruteforce():
    rnd = random.Random(7)

    def ed(x, y):
        pr = list(range(len(y) + 1))
        for i, cx in enumerate(x, 1):
            cu = [i]
            for j, cy in enumerate(y, 1):
                cu.append(min(pr[j] + 1, cu[-1] + 1, pr[j - 1] + (cx != cy)))
            pr = cu
        return pr[-1]

    for _ in range(300):
        p = "".join(rnd.choice("ab1 ") for _ in range(rnd.randint(1, 6)))
        t = "".join(rnd.choice("ab1 ") for _ in range(rnd.randint(0, 12)))
        assert _search_row(p, t) == search_row_naive(p, t)
        fm = fuzzy_match(p, t)
        allw = {(i, j): ed(p, t[i:j]) for i in range(len(t) + 1) for j in range(i, len(t) + 1)}
        best = min(allw.values())
        assert fm.d_min == best and fm.windows() == sorted(k for k, v in allw.items() if v == best)


def test_s12_persis_seluruh_unit():
    r = verify(A12, "(2) Modal dasar dibagi atas saham.")
    assert (r.exists, r.faithful, r.faithful_score, r.valid_on_date, r.status_table_version) == (
        "lulus", "lulus", None, "tidak_dijalankan", None)


def test_s13_persis_sebagian():
    for t in ("Perseroan wajib berbadan hukum.", "Perseroan wajib berbadan hukum", "wajib"):
        assert fz(A11, t) == ("lulus", None)


def test_s14_kalimat_unit_lain():
    assert fz(A11, "Modal dasar dibagi atas saham.") == ("gagal", F(11, 30))


def test_s15_parafrase():
    assert fz(A11, "Perseroan harus berstatus badan hukum.") == ("gagal", F(27, 38))


def test_s16_satu_kata_diubah_dan_konfigurasi():
    assert fz(A11, "Perseroan dapat berbadan hukum.") == ("gagal", F(27, 31))
    assert fz(A11, "Perseroan boleh berbadan hukum.") == ("gagal", F(26, 31))
    assert fz(A11, "Perseroan dapat berbadan hukum.", cfg("0.85", 4)) == ("lulus", F(27, 31))
    assert fz(A11, "Perseroan dapat berbadan hukum.", cfg("0.85", 3)) == ("gagal", F(27, 31))


def test_s17_negasi():
    assert fz(A11, "Perseroan tidak wajib berbadan hukum.") == ("gagal", F(31, 37))


def test_s18_angka_diubah_v3_on():
    q = "Rapat diadakan paling lambat 80 hari setelah tahun buku berakhir."
    assert len(q) == 65 and fz(A31, q) == ("gagal", F(64, 65))
    assert fz(A31, q, cfg(v3_on=False))[0] == "lulus"  # bukti: hanya pengaman angka yang menolak
    assert fz(A31, "Rapat diadakan paling lambat 30 hari setelah tahun buku berakhir.") == ("lulus", None)


def test_s19_spasi_dan_huruf_awal():
    assert fz(A11, "Perseroan wajib berbadan hukum. ") == ("lulus", F(31, 32))
    assert fz(A11, "Perseroan wajib  berbadan hukum.") == ("lulus", F(31, 32))
    assert fz(A11, "perseroan wajib berbadan hukum.") == ("lulus", F(30, 31))
    assert fz(A11, "Perseroan wajib berbadan hukum.x") == ("lulus", F(31, 32))


def test_s20_ambang_inklusif_dan_konfigurasi():
    b, c = "wajib berbadam hukun", "Laporan disampaikan tertulis."
    assert fz(A11, "wajib berbadan hukun") == ("lulus", F(19, 20))
    assert fz(A11, b) == ("gagal", F(18, 20))
    assert fz(A32, c) == ("gagal", F(27, 29))
    assert fz(A11, b, cfg("0.90"))[0] == "lulus" and fz(A32, c, cfg("0.90"))[0] == "lulus"
    assert fz(A32, c, cfg("0.85"))[0] == "lulus"


def test_s21_code_point_bukan_utf16():
    assert fz(A32, "aporan \U0001D4B3 disampaikan") == ("lulus", F(19, 20))


def test_s22_kutipan_kosong():
    for t in ("", "   "):
        r = verify(A11, t)
        assert (r.exists, r.faithful, r.faithful_score) == ("lulus", "gagal", None)


def test_s23_lebih_panjang_dari_unit():
    assert fz(A11, "Perseroan wajib berbadan hukum. Modal") == ("gagal", F(31, 37))


def test_s25_beberapa_kutipan():
    out = {"status": "jawab", "jawaban": "x", "kutipan": [
        {"alamat": A11, "teks": "(1) Perseroan wajib berbadan hukum."},
        {"alamat": a("Pasal 1", "ayat (3)"), "teks": "x"},
        {"alamat": A12, "teks": "Modal dasar dibagi atas sahamm."},
        {"alamat": A11, "teks": "(1) Perseroan wajib berbadan hukum."}]}
    rs = verify_answer("ans", out, UNITS, [], OP)
    assert [r.citation_index for r in rs] == [0, 1, 2, 3]
    assert [(r.exists, r.faithful, r.faithful_score) for r in rs] == [
        ("lulus", "lulus", None), ("gagal", "gagal", None), ("lulus", "lulus", F(30, 31)), ("lulus", "lulus", None)]
    assert verify_answer("ans", {"status": "tolak", "jawaban": None, "kutipan": []}, UNITS, [], OP) == []


def test_s26_murni(monkeypatch):
    units, out = copy.deepcopy(UNITS), {"kutipan": [{"alamat": A32, "teks": "Laporan disampaikan tertulis."}]}
    before = (copy.deepcopy(units), copy.deepcopy(out))

    def boom(*_a, **_k):
        raise AssertionError("I/O dilarang")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr("builtins.open", boom)
    r1 = verify_answer("x", out, units, [], OP)
    r2 = verify_answer("x", out, units, [], OP)
    assert r1 == r2 and repr(r1) == repr(r2)
    r3 = verify_answer("x", out, units, [], cfg("0.90"))
    assert r1[0].faithful == "gagal" and r3[0].faithful == "lulus"
    q = {"kutipan": [{"alamat": A11, "teks": "Perseroan dapat berbadan hukum."}]}
    assert verify_answer("x", q, units, [], cfg("0.85", 3))[0].faithful == "gagal"
    assert verify_answer("x", q, units, [], cfg("0.85", 4))[0].faithful == "lulus"
    assert (units, out) == before


def test_s35_kutipan_panjang_q1():
    base = P4[4:]
    assert len(base) == 156
    assert fz(A41, base) == ("lulus", None)
    assert fz(A41, base.replace("wajib ", "wajib tidak ", 1)) == ("gagal", F(26, 27))
    assert fz(A41, base.replace("wajib", "dapat")) == ("gagal", F(38, 39))
    assert fz(A41, base.replace("enam", "tiga")) == ("gagal", F(38, 39))
    assert fz(A41, base + " ") == ("lulus", F(156, 157))


def test_s36_multi_dokumen_dan_teks_berulang():
    pa = f"{'Perppu 2/2099'} › Pasal 1 › ayat (1)"
    kw = dict(units=UUPT_MAP)
    assert fz(pa, "Perseroan dilarang berbadan hukum asing.", **kw) == ("lulus", None)
    assert fz(A11, "Perseroan dilarang berbadan hukum asing.", **kw) == ("gagal", F(27, 40))
    assert fz(pa, "Perseroan wajib berbadan hukum.", **kw) == ("gagal", F(23, 31))
    assert fz(a("Penjelasan", "Pasal 2"), "Cukup jelas.", **kw) == ("lulus", None)
    assert fz(a("Penjelasan", "Pasal 3"), "Cukup jelas.", **kw) == ("lulus", None)
    assert fz(a("Pasal 2"), "Cukup jelas.", **kw) == ("gagal", F(3, 12))


def test_s37_huruf_kutipan_pendek_lf():
    h = a("Pasal 5", "ayat (1)")
    assert fz(h + " › huruf a", "a. membayar pajak;") == ("lulus", None)
    for bad in (h + " › huruf c", h + " › Huruf a", a("Pasal 5", "huruf a")):
        assert verify(bad, "x").exists == "gagal"
    for t in (".", "a", "(1)"):
        assert fz(A11, t) == ("lulus", None)
    assert fz(h, "Direksi wajib:\na. membayar pajak;") == ("lulus", None)
    assert fz(h, "Direksi wajib: a. membayar pajak;") == ("lulus", F(32, 33))


def test_s39_fuzzy_lulus_memakai_seluruh_unit():
    r = verify(A12, "dasar dibagi atas sahamm.", ch=chunks("cf"))
    assert (r.faithful, r.faithful_score, r.matched_chunk_id) == ("lulus", F(24, 25), "cf")
    r = verify(a("Pasal 6"), "Direksi menyampaikan laporan", ch=chunks("cq2", "cq1"))
    assert (r.faithful, r.faithful_score, r.matched_chunk_id) == ("lulus", None, "cq1")


def test_s40_pengaman_angka_rincian():
    q = "Rapat diadakan paling lambat "
    s = " hari setelah tahun buku berakhir."
    exp = {
        "a": (q + "3" + s, "gagal"), "b": ("Rapat diadakan paling lambat" + s, "gagal"),
        "c": (q + "30" + s[:-1] + "r.", "lulus"), "d": (q + "300" + s, "gagal"),
        "e": ("0 hari setelah tahun buku berakhirr.", "gagal"), "f": (q + "30 hri setelah tahun buku berakhir.", "lulus"),
    }
    sc = {"a": F(63, 64), "b": F(59, 62), "c": F(65, 66), "d": F(65, 66), "e": F(35, 36), "f": F(63, 64)}
    for k, (t, want) in exp.items():
        assert fz(A31, t) == (want, sc[k]), k
    assert fz(A31, "(1) " + q + "30" + s[:-1] + "r.") == ("lulus", F(69, 70))  # j
    assert fz(A81, "Denda paling banyak 1500 rupiah dan 2 kali pemeriksaan pada 12 Maret.") == ("lulus", None)  # g
    assert fz(A81, "Denda paling banyak 1500 rupiah dan 2 kali pemeriksaan pada 21 Maret.") == ("gagal", F(67, 69))  # h
    assert fz(A81, "Denda paling banyak 1500 rupiah dan kali pemeriksaan pada 12 Maret.") == ("gagal", F(65, 67))  # i
    assert fz(A71, "Direksi mencatat kode 12 bxru sekali.") == ("lulus", F(36, 37))  # k1
    assert fz(A71, "Direksi mencatat kode 13 baru sekali.") == ("lulus", F(36, 37))  # k2
    assert fz(A31, "Rapat diadkan paling lambat 3") == ("gagal", F(28, 29))  # l1
    assert fz(A31, "Rapat diadakan paling lambat 3") == ("lulus", None)  # l2
    assert fz(A11, "(2) Perseroan wajib berbadan hukum.") == ("gagal", F(34, 35))  # m
    u = "Biaya administrasi sebesar {} rupiah dibayar tunai kepada kas negara."
    assert fz(A82, u.format("1,000")) == ("lulus", F(71, 72))  # n1
    assert fz(A82, u.format("1000")) == ("gagal", F(70, 71))  # n2
    assert fz(A82, u.format("1.00")) == ("gagal", F(70, 71))  # n3
    assert verify(A82, u.format("1000")).exists == "lulus"


def test_s41_d_max_inklusif_konfigurasi():
    base = P4[4:]
    A = base.replace("enam bulan", "enap bulan")
    B = base.replace("enam bulan", "enxy bulan")
    C = base.replace("enam bulan", "enxyl bulan")
    assert fz(A41, A) == ("lulus", F(155, 156))
    assert fz(A41, B) == ("lulus", F(154, 156))
    assert fz(A41, C) == ("lulus", F(154, 157))
    assert fz(A41, C, cfg(d_max=2)) == ("gagal", F(154, 157))
    assert fz(A41, B, cfg(d_max=2))[0] == "lulus"
    assert fz(A41, A, cfg(d_max=0)) == ("gagal", F(155, 156))
    assert fz(A41, base, cfg(d_max=0)) == ("lulus", None)
    assert fz(A11, "wajib berbadam hukun", cfg("0.95", 3)) == ("gagal", F(18, 20))


# --- tindak lanjut review (SHOULD-1, NIT-1) ---
def _mini(addr, text, start=0):
    from backend.verifier import AddressUnit
    return {addr: AddressUnit(addr, start, start + len(text), text)}


def test_v3_urutan_deret_tertukar_gagal():
    """Deret digit dibandingkan sebagai DAFTAR berurutan, bukan himpunan: sumber '30 ... 60', kutipan '60 ... 30'."""
    src = "(1) Nilai 30 dan nilai 60 dicatat dalam buku besar tahunan perseroan setiap tahun."
    q = "Nilai 60 dan nilai 30 dicatat dalam buku besar tahunan perseroan setiap tahun."
    u = _mini("U", src)
    r = verify("U", q, units=u)
    assert r.exists == "lulus" and r.faithful == "gagal" and r.faithful_score == F(len(q) - 2, len(q))
    assert fz("U", q, cfg(v3_on=False), units=u)[0] == "lulus"  # hanya pengaman angka yang menolak


def test_v3_duplikat_digit_gagal():
    """Daftar, bukan multiset/himpunan: sumber '3 ... 3', kutipan '3' (satu kali)."""
    src = "(1) Kode 3 3 dicatat dalam buku besar tahunan perseroan setiap tahun."
    q = "Kode 3 dicatat dalam buku besar tahunan perseroan setiap tahun."
    u = _mini("U", src)
    r = verify("U", q, units=u)
    assert r.faithful == "gagal" and r.faithful_score == F(len(q) - 2, len(q))
    assert fz("U", q, cfg(v3_on=False), units=u)[0] == "lulus"


def test_s39_rentang_tertaut_fuzzy_potongan_beririsan_di_ujung_unit():
    from backend.verifier import ChunkSpan
    q = "dasar dibagi atas sahamm."  # fuzzy lulus; jendela Sellers [54,78), rentang tertaut = seluruh unit [44,78)
    lead = ChunkSpan("lead", 30, 45)  # hanya karakter 44 (awal unit)
    tail = ChunkSpan("tail", 77, 100)  # hanya karakter 77 (akhir unit)
    off = ChunkSpan("off", 78, 100)  # menempel, tak beririsan
    for order, want in ((["lead", "tail"], "lead"), (["tail", "lead"], "tail")):
        by = {"lead": lead, "tail": tail}
        r = verify(A12, q, ch=[by[n] for n in order])
        assert (r.faithful, r.matched_chunk_id) == ("lulus", want)
    assert verify(A12, q, ch=[off]).matched_chunk_id is None
    assert verify(A12, q, ch=[lead]).matched_chunk_id == "lead"  # jendela Sellers saja tidak akan menyentuhnya
