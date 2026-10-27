"""M2.3 ringkasan 2x2 dan matched_chunk_id (S27, S29-S34, S38)."""

import copy
import random

from backend.verifier import grade_answer, summarize

from .verifier_fixtures import OP, UNITS, a, chunks, verify

A11 = a("Pasal 1", "ayat (1)")
A12 = a("Pasal 1", "ayat (2)")
T11 = "(1) Perseroan wajib berbadan hukum."
T12 = "(2) Modal dasar dibagi atas saham."


def ans(status, *cites):
    return {"status": status, "jawaban": None if status != "jawab" else "j",
            "kutipan": [{"alamat": x, "teks": t} for x, t in cites]}


def cell(status, cites, ch, gold):
    return grade_answer("x", ans(status, *cites), UNITS, chunks(*ch), gold, OP)[1]


G1 = [(8, 43)]
ITEMS = {  # S29
    "i1": ("jawab", [(A11, T11)], ["c1", "c2"], G1),
    "i2": ("jawab", [(A12, T12)], ["c1", "c2"], G1),
    "i2b": ("jawab", [(A12, T12)], ["c1"], G1),
    "i3": ("jawab", [], ["c1"], G1),
    "i4": ("jawab", [(A11, T11)], ["c1"], []),
    "i5": ("jawab", [(A11, T11), (a("Pasal 1", "ayat (3)"), "x")], ["c1"], G1),
    "i6": ("bukti_tidak_cukup", [], ["c2"], G1),
    "i7": ("tolak", [], ["c1", "c2"], []),
    "i8": ("tolak", [], ["c1"], G1),
    "i9": ("bukti_tidak_cukup", [(A11, T11)], ["c1"], G1),
    "i10": ("tolak", [], ["c2"], [(8, 78)]),
    "i11": ("tolak", [], ["c1"], [(43, 44)]),
    "i1b": ("jawab", [(A11, T11)], ["c1"], [(42, 43)]),
    "i12": ("jawab", [(A12, T12)], ["c2"], [(44, 45)]),
    "i13": ("tolak", [], ["c2"], [(44, 45)]),
}
S29 = ["i1", "i2", "i2b", "i3", "i4", "i5", "i6", "i7", "i8", "i9", "i10", "i11"]
WANT = {"i1": "answered_supported", "i2": "answered_unsupported", "i2b": "answered_unsupported",
        "i3": "answered_unsupported", "i4": "answered_unsupported", "i5": "answered_unsupported",
        "i6": "abstained_correct", "i7": "abstained_correct", "i8": "abstained_should_answer",
        "i9": "abstained_should_answer", "i10": "abstained_should_answer", "i11": "abstained_correct",
        "i1b": "answered_supported", "i12": "answered_supported", "i13": "abstained_should_answer"}


def cells_of(names, profile="contributor"):
    return [("S", "best", profile, cell(*ITEMS[n])) for n in names]


def test_s29_sel_per_butir_dan_jumlah():
    for n in S29:
        assert cell(*ITEMS[n]) == WANT[n], n
    (s,) = summarize(cells_of(S29))
    assert (s.answered_supported, s.answered_unsupported, s.abstained_correct, s.abstained_should_answer, s.n_items) == (
        1, 5, 3, 3, 12)
    assert all(isinstance(v, int) for v in s.to_dict().values() if not isinstance(v, str))


def test_s30_batas_irisan():
    for n in ("i1b", "i11", "i12", "i13"):
        assert cell(*ITEMS[n]) == WANT[n], n


def test_s31_nol_dan_butir_tanpa_jawaban():
    key = ("S", "best", "contributor")
    (z,) = summarize([], keys=[key])
    assert (z.answered_supported, z.answered_unsupported, z.abstained_correct, z.abstained_should_answer, z.n_items) == (0,) * 5
    (s,) = summarize(cells_of(["i1", "i8"]), keys=[key])
    assert s.n_items == 2  # butir ketiga tanpa AnswerRecord tidak ikut


def test_s32_ringkasan_per_kunci():
    runs = {
        ("S-best", "best", "contributor"): {"i1": ITEMS["i1"], "i8": ITEMS["i8"]},
        ("S-base", "baseline", "contributor"): {"i1": ("tolak", [], ["c1", "c2"], G1), "i8": ITEMS["i8"]},
        ("S-best", "best", "glimmer_local"): {"i1": ("jawab", [], ["c1", "c2"], G1),
                                              "i8": ("jawab", [(A11, T11)], ["c1"], G1)},
        ("S-best", "best", "spark_open_baseten"): {"i1": ("jawab", [(A12, T12)], ["c1", "c2"], G1), "i8": ITEMS["i8"]},
    }
    entries = [(*k, cell(*v)) for k, items in runs.items() for v in items.values()]
    got = {(s.setting_id, s.slot, s.model_profile): (s.answered_supported, s.answered_unsupported, s.abstained_correct,
                                                     s.abstained_should_answer, s.n_items) for s in summarize(entries)}
    assert got == {("S-best", "best", "contributor"): (1, 0, 0, 1, 2), ("S-base", "baseline", "contributor"): (0, 0, 0, 2, 2),
                   ("S-best", "best", "glimmer_local"): (1, 1, 0, 0, 2),
                   ("S-best", "best", "spark_open_baseten"): (0, 1, 0, 1, 2)}


def test_s33_urutan_dan_tanpa_mutasi():
    base = summarize(cells_of(S29))
    rnd = random.Random(3)
    for _ in range(5):
        names = S29[:]
        rnd.shuffle(names)
        assert summarize(cells_of(names)) == base
        st, cites, ch, g = ITEMS["i5"]
        cites = cites[:]
        rnd.shuffle(cites)
        assert cell(st, cites, ch, g) == "answered_unsupported"
    out = ans("jawab", (A11, T11), (a("Pasal 1", "ayat (3)"), "x"))
    snap = copy.deepcopy(out)
    grade_answer("x", out, UNITS, chunks("c1"), G1, OP)
    assert out == snap and out["status"] == "jawab"


def test_s34_potongan_bertumpang():
    g = [(65, 70)]
    mid = lambda r: r.matched_chunk_id  # noqa: E731
    r = verify(A12, T12, ch=chunks("ca", "cb"))
    assert mid(r) == "ca" and cell("jawab", [(A12, T12)], ["ca", "cb"], g) == "answered_supported"
    r = verify(A12, "(2) Modal dasar", ch=chunks("ca", "cb"))
    assert mid(r) == "ca" and cell("jawab", [(A12, "(2) Modal dasar")], ["ca", "cb"], g) == "answered_supported"
    r = verify(A12, "dibagi atas saham.", ch=chunks("ca", "cb"))
    assert mid(r) == "cb" and cell("jawab", [(A12, "dibagi atas saham.")], ["ca", "cb"], g) == "answered_supported"
    r = verify(A12, T12, ch=chunks("cb", "ca"))
    assert mid(r) == "cb" and cell("jawab", [(A12, T12)], ["cb", "ca"], g) == "answered_supported"
    assert cell("jawab", [(A12, T12)], ["ca", "cb"], [(8, 20)]) == "answered_supported"  # kelemahan V10-any (C10)


def test_s27_matched_chunk_id():
    def mid(teks, names, addr=A12):
        return verify(addr, teks, ch=chunks(*names)).matched_chunk_id

    assert mid(T12, ["c2b", "c2"]) == "c2b"
    assert mid(T12, ["c1x"]) is None
    assert mid(T12, ["c1y", "c2"]) == "c1y"
    assert mid("dibagi atas saham.", ["c1y", "c2b", "c2"]) == "c2b"
    assert mid("x", ["c2b", "c2"], a("Pasal 1", "ayat (3)")) is None
    assert mid(T12, ["c3"]) is None


def test_s38_minimal_satu_mendukung():
    k0, k1 = (A11, T11), (A12, T12)
    assert cell("jawab", [k0, k1], ["c1", "c2"], G1) == "answered_supported"
    assert cell("jawab", [k1, k0], ["c1", "c2"], G1) == "answered_supported"
    assert cell("jawab", [k0, (a("Pasal 2"), "Perseroan berkedudukan di kota.")], ["c1"], G1) == "answered_supported"
    assert cell("jawab", [(a("Pasal 2"), "Perseroan berkedudukan di kota."), k0], ["c1"], G1) == "answered_supported"
