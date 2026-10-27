"""M2.3 uji 1 Exists dan konfigurasi (S1-S11, S24, S28)."""

import math
import time
from fractions import Fraction

import pytest

from backend import config as appcfg
from backend.verifier import VerifierConfigError, fuzzy_match, load_verifier_config, parse_verifier_config

from .verifier_fixtures import AKTA_MAP, OP, UNITS, UUPT_MAP, a, cfg, verify
from .verifier_fixtures import PERPPU


def gagal2(r):
    assert r.exists == "gagal" and r.faithful == "gagal" and r.faithful_score is None and r.matched_chunk_id is None


def test_s1_unit_ayat_exists():
    r = verify(a("Pasal 1", "ayat (1)"), "(1) Perseroan wajib berbadan hukum.")
    assert r.exists == "lulus"


def test_s2_pasal_tanpa_ayat():
    r = verify(a("Pasal 2"), "Perseroan berkedudukan di kota.")
    assert (r.exists, r.faithful, r.faithful_score) == ("lulus", "lulus", None)


def test_s3_alamat_salah_ayat():
    for addr in (a("Pasal 1", "ayat (3)"), a("Pasal 3", "ayat (0)"), a("Pasal 2", "ayat (1)")):
        gagal2(verify(addr, "x"))


def test_s4_nomor_pasal_tidak_ada():
    for addr in (a("Pasal 9", "ayat (1)"), a("Pasal 10")):
        assert verify(addr, "x").exists == "gagal"


def test_s5_bagian_salah():
    for addr in (a("Penjelasan", "Pasal 3", "Ayat (2)"), a("Pasal 1", "Ayat (1)"),
                 a("Penjelasan", "Pasal 2", "ayat (1)"), a("Pasal 3")):
        assert verify(addr, "x").exists == "gagal"


def test_s6_bagian_tertukar_alamat_ada():
    r = verify(a("Penjelasan", "Pasal 1", "Ayat (1)"), "Perseroan wajib berbadan hukum.")
    assert r.exists == "lulus" and r.faithful == "gagal" and r.faithful_score == Fraction(13, 31)


def test_s7_variasi_alamat_ditolak():
    for addr in ("UU 9/2099 > Pasal 1 > ayat (1)", a("Pasal 1", "ayat (1)") + " ", "UU 9/2099 › Pasal  1 › ayat (1)",
                 "uu 9/2099 › Pasal 1 › ayat (1)", "UU 9/2099 › Pasal 1 › ayat 1"):
        assert verify(addr, "(1) Perseroan wajib berbadan hukum.").exists == "gagal", addr


def test_s8_peraturan_lain():
    for addr in ("UU 7/2098 › Pasal 1 › ayat (1)", "UU 9/2098 › Pasal 1 › ayat (1)", "Perpu 9/2099 › Pasal 1 › ayat (1)"):
        gagal2(verify(addr, "(1) Perseroan wajib berbadan hukum.", units=UUPT_MAP))


def test_s9_rentang_v5_strict_tanpa_skor():
    calls = []

    def scorer(q, t):
        calls.append(1)
        return fuzzy_match(q, t)

    r1, r2, r3 = a("Pasal 1", "ayat (1)"), a("Pasal 1", "ayat (2)"), None
    for addr in (f"{r1} – {r2}", f"{r2} – {r1}", f"{r1} - {r2}"):
        gagal2(verify(addr, "Modal dasar dibagi atas saham.", scorer=scorer))
    assert calls == []


def test_s10_peta_per_keluarga():
    r = verify("AKTA-X › Badan › Pasal 1", "Harga disepakati.", units=AKTA_MAP)
    assert (r.exists, r.faithful, r.faithful_score) == ("lulus", "lulus", None)
    assert verify(a("Pasal 2"), "x", units=AKTA_MAP).exists == "gagal"
    assert verify("AKTA-X › Badan › Pasal 1", "x", units=UNITS).exists == "gagal"


def test_s11_alamat_kosong_dan_panjang():
    t0 = time.time()
    for addr in ("", "   ", "a" * 10000):
        assert verify(addr, "x").exists == "gagal"
    assert time.time() - t0 < 1


def test_s24_uji1_gagal_tidak_diselamatkan():
    calls = []

    def scorer(q, t):
        calls.append(1)
        return fuzzy_match(q, t)

    gagal2(verify(a("Pasal 1", "ayat (5)"), "(1) Perseroan wajib berbadan hukum.", scorer=scorer))
    assert calls == []


@pytest.mark.parametrize("bad", [0, "0", "-0.1", -0.1, "1.01", 1.01, float("nan"), "0,95", None, "", True, "abc", math.inf])
def test_s28_theta_invalid(bad):
    with pytest.raises(VerifierConfigError):
        parse_verifier_config({"theta": bad, "d_max": 3, "v3_on": True})


@pytest.mark.parametrize("bad", [-1, 2.5, "3", True, None, False])
def test_s28_d_max_invalid(bad):
    with pytest.raises(VerifierConfigError):
        parse_verifier_config({"theta": "0.95", "d_max": bad, "v3_on": True})


def test_s28_missing_keys_no_hidden_default():
    for drop in ("theta", "d_max", "v3_on"):
        raw = {"theta": "0.95", "d_max": 3, "v3_on": True}
        del raw[drop]
        with pytest.raises(VerifierConfigError):
            parse_verifier_config(raw)
    with pytest.raises(VerifierConfigError):
        parse_verifier_config({"theta": "0.95", "d_max": 3, "v3_on": "yes"})


def test_s28_valid_values_exact_rationals():
    assert parse_verifier_config({"theta": "0.95", "d_max": 3, "v3_on": True}).theta == Fraction(19, 20)
    assert parse_verifier_config({"theta": 0.9, "d_max": 0, "v3_on": True}).theta == Fraction(9, 10)  # bukan float biner
    c = parse_verifier_config({"theta": 1.0, "d_max": 3, "v3_on": True})
    assert c.theta == 1
    assert verify(a("Pasal 1", "ayat (1)"), "wajib berbadan hukun", conf=c).faithful == "gagal"  # S20(a) pada 1,0
    assert verify(a("Pasal 1", "ayat (1)"), "Perseroan wajib berbadan hukum. ", conf=c).faithful == "gagal"  # S19(a)
    assert verify(a("Pasal 2"), "Perseroan berkedudukan di kota.", conf=c).faithful == "lulus"  # S12


def test_real_config_file_is_h067():
    c = load_verifier_config()
    assert c.theta == Fraction(19, 20) and c.d_max == 3 and c.v3_on is True
    assert appcfg.load("verifier")["version"] == 1


def test_config_missing_file(tmp_path):
    with pytest.raises(VerifierConfigError):
        load_verifier_config(tmp_path)
