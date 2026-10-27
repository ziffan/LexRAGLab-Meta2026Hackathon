"""Data sintetis M2.3 (docs/scenarios/M2.3.md): peta mainan UU-X ("UU 9/2099"), Perppu 2/2099, AKTA-X, potongan."""

from __future__ import annotations

from fractions import Fraction

from backend.verifier import AddressUnit, ChunkSpan, VerifierConfig, parse_verifier_config, verify_citation

P = "UU 9/2099"
SEP = " › "


def a(*parts: str) -> str:
    return SEP.join([P, *parts])


LINES = [
    "Pasal 1",
    "(1) Perseroan wajib berbadan hukum.",
    "(2) Modal dasar dibagi atas saham.",
    "Pasal 2",
    "Perseroan berkedudukan di kota.",
    "Pasal 3",
    "(1) Rapat diadakan paling lambat 30 hari setelah tahun buku berakhir.",
    "(2) Laporan \U0001F600 disampaikan tertulis.",
    "Penjelasan Pasal 1",
    "Ayat (1) Badan hukum ialah subjek hukum.",
    "Ayat (2) Cukup jelas.",
    "Penjelasan Pasal 2",
    "Cukup jelas.",
    "Penjelasan Pasal 3",
    "Cukup jelas.",
]
TEXT = "\n".join(LINES) + "\n"
assert len(TEXT) == 379

# alamat -> (start, end) pada TEXT
_SPANS = {
    a("Pasal 1", "ayat (1)"): (8, 43),
    a("Pasal 1", "ayat (2)"): (44, 78),
    a("Pasal 2"): (87, 118),
    a("Pasal 3", "ayat (1)"): (127, 196),
    a("Pasal 3", "ayat (2)"): (197, 232),
    a("Penjelasan", "Pasal 1", "Ayat (1)"): (252, 292),
    a("Penjelasan", "Pasal 1", "Ayat (2)"): (293, 314),
    a("Penjelasan", "Pasal 2"): (334, 346),
    a("Penjelasan", "Pasal 3"): (366, 378),
}
UNITS: dict[str, AddressUnit] = {k: AddressUnit(k, s, e, TEXT[s:e]) for k, (s, e) in _SPANS.items()}
assert UNITS[a("Pasal 1", "ayat (1)")].text == "(1) Perseroan wajib berbadan hukum."
assert UNITS[a("Pasal 3", "ayat (2)")].text == "(2) Laporan \U0001F600 disampaikan tertulis."

# Unit tambahan (offset tidak dipakai kecuali Pasal 6)
P4 = ("(1) Direksi wajib menyampaikan laporan tahunan kepada rapat umum pemegang saham paling lambat enam bulan "
      "setelah tahun buku berakhir dan menyimpannya di kantor.")
assert len(P4) == 160
P5 = "(1) Direksi wajib:\na. membayar pajak;\nb. menyimpan buku."
P6 = "Direksi menyampaikan laporan. Direksi menyampaikan laporan kepada komisaris."
assert len(P6) == 76
_EXTRA = {
    a("Pasal 4", "ayat (1)"): (1000, 1160, P4),
    a("Pasal 5", "ayat (1)"): (1200, 1200 + len(P5), P5),
    a("Pasal 5", "ayat (1)", "huruf a"): (1213, 1230, "a. membayar pajak;"),
    a("Pasal 5", "ayat (1)", "huruf b"): (1231, 1249, "b. menyimpan buku."),
    a("Pasal 7", "ayat (1)"): (1400, 1480,
                                "(1) Direksi mencatat kode 12 baru sekali. Direksi mencatat kode 13 bxru sekali."),
    a("Pasal 8", "ayat (2)"): (1500, 1580,
                                "(2) Biaya administrasi sebesar 1.000 rupiah dibayar tunai kepada kas negara."),
    a("Pasal 8", "ayat (1)"): (1600, 1673,
                                "(1) Denda paling banyak 1500 rupiah dan 2 kali pemeriksaan pada 12 Maret."),
    a("Pasal 6"): (400, 476, P6),
}
for _k, (_s, _e, _t) in _EXTRA.items():
    UNITS[_k] = AddressUnit(_k, _s, _e, _t)
assert len(UNITS[a("Pasal 8", "ayat (1)")].text) == 73

PERPPU = "Perppu 2/2099"
PERPPU_UNIT = AddressUnit(f"{PERPPU}{SEP}Pasal 1{SEP}ayat (1)", 3000, 3040, "(1) Perseroan dilarang berbadan hukum asing.")
UUPT_MAP: dict[str, AddressUnit] = {**UNITS, PERPPU_UNIT.address: PERPPU_UNIT}

AKTA_MAP: dict[str, AddressUnit] = {
    "AKTA-X › Kepala": AddressUnit("AKTA-X › Kepala", 0, 19, "Para pihak sepakat."),
    "AKTA-X › Badan › Pasal 1": AddressUnit("AKTA-X › Badan › Pasal 1", 20, 37, "Harga disepakati."),
}

CH = {  # potongan mainan [start, end)
    "c1": (0, 43), "c2": (44, 118), "c3": (119, 232), "c4": (233, 314), "c5": (315, 378), "cf": (0, 50),
    "cq1": (400, 429), "cq2": (429, 476), "c1x": (0, 44), "c1y": (0, 45), "c2b": (60, 100), "ca": (0, 60),
    "cb": (40, 118),
}


def chunks(*names: str) -> list[ChunkSpan]:
    return [ChunkSpan(n, *CH[n]) for n in names]


OP = parse_verifier_config({"theta": "0.95", "d_max": 3, "v3_on": True})


def cfg(theta: str = "0.95", d_max: int = 3, v3_on: bool = True) -> VerifierConfig:
    return parse_verifier_config({"theta": theta, "d_max": d_max, "v3_on": v3_on})


def verify(alamat: str, teks: str, *, units=None, ch=(), conf: VerifierConfig = OP, scorer=None):
    """Hasil `VerifierResult` satu kutipan."""
    return verify_citation({"alamat": alamat, "teks": teks}, units if units is not None else UNITS, list(ch), conf,
                           scorer=scorer).result


def verdict(alamat: str, teks: str, *, units=None, ch=(), conf: VerifierConfig = OP):
    return verify_citation({"alamat": alamat, "teks": teks}, units if units is not None else UNITS, list(ch), conf)


def lulus(r) -> bool:
    return r.exists == "lulus" and r.faithful == "lulus"


F = Fraction
