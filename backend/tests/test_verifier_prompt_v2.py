"""M2.3 S42: prompt C v2 dan label alamat unit (H-067 V5 (i), H-070). Struktural; tanpa model, jaringan, atau .env."""

import hashlib
import json

from backend.answer.context import ContextEntry, entry_labels, render, unit_label
from backend.answer.prompt import load_prompt, prompt_versions
from backend.chunking.address_map import AddressMap, Unit
from backend.config import REPO_ROOT

from .verifier_fixtures import TEXT, UNITS, a

V1_SHA256 = "0882b79aa79c110408a62f8bc7b4aeeb2c714cc5a5fbed274088e47bc5310a77"
PDIR = REPO_ROOT / "prompts" / "c"
SEP = " › "


def toy_map() -> AddressMap:
    us = []
    for addr in (a("Pasal 1", "ayat (1)"), a("Pasal 1", "ayat (2)"), a("Pasal 2")):
        u = UNITS[addr]
        us.append(Unit("ayat", "batang_tubuh", u.start, u.end, addr, (("peraturan", "UU 9/2099"),)))
    return AddressMap(us)


def entries(labelled: bool):
    amap = toy_map()
    cm = ContextEntry("cm", a("Pasal 1", "ayat (1)") + " – " + a("Pasal 2"), TEXT[8:118], 40, 1,
                      entry_labels(amap, 8, 118) if labelled else ())
    c1 = ContextEntry("c1", a("Pasal 2"), TEXT[87:118], 10, 2, entry_labels(amap, 87, 118) if labelled else ())
    return cm, c1


def test_a_versions_json_dan_v1_tak_berubah():
    meta = json.loads((PDIR / "versions.json").read_text(encoding="utf-8"))
    assert meta["current"] == "v2" and "v1" in meta["versions"] and "v2" in meta["versions"]
    v1, v2 = (PDIR / "v1.md").read_bytes(), (PDIR / "v2.md").read_bytes()
    assert hashlib.sha256(v1).hexdigest() == V1_SHA256
    assert hashlib.sha256(v2).hexdigest() != V1_SHA256
    assert load_prompt("v1").prompt_hash != load_prompt("v2").prompt_hash
    assert load_prompt().version == "v2" and prompt_versions() == ["v2", "v1"]
    assert load_prompt("v1").unit_labels is False and load_prompt("v2").unit_labels is True


def test_b_inti_v1_dipertahankan():
    t = load_prompt("v2").template
    for tok in ("<data-KODE>", "</data-KODE>", "`ALAMAT:`", "`TEKS:`", "PERSIS", "jawab", "bukti_tidak_cukup", "tolak",
                "hanya objek JSON"):
        assert tok in t, tok


def test_c_butir_aturan_alamat_unit():
    t = load_prompt("v2").template
    rule = next(p for p in t.split("\n") if "–" in p)
    low = rule.lower()
    assert "label" in low and "rentang" in low and "–" in rule and ("satu unit" in t.lower() or "alamat unit" in t.lower())
    assert "label" in t.lower() and "alamat unit" in t.lower()


def test_d_tanpa_nama_setting_dan_kepala_identik():
    t = load_prompt("v2").template.lower()
    for w in ("baseline", "best", "terbaik", "fixed_size", "structure_handwritten", "bm25", "hybrid", "kolom", "profil",
              "setting"):
        assert w not in t, w
    p = load_prompt("v2")
    best_text, _ = render(p, "q?", list(entries(True)))
    base_text, _ = render(p, "q?", [entries(True)[0]])
    head = p.template.rstrip()
    assert best_text.startswith(head) and base_text.startswith(head)
    # instruksi alamat unit hanya di kepala (pesan sistem), tidak di bagian per-kolom
    rest = best_text[len(head):]
    assert "bukan alamat unit" not in rest and "rentang" not in rest


def test_e_label_unit_h070():
    amap = toy_map()
    cm, c1 = entries(True)
    shown = cm.shown()
    labs = [unit_label(a("Pasal 1", "ayat (1)")), unit_label(a("Pasal 1", "ayat (2)")), unit_label(a("Pasal 2"))]
    assert all(shown.count(x) == 1 for x in labs)
    assert [shown.index(x) for x in labs] == sorted(shown.index(x) for x in labs)  # urutan dokumen
    assert shown.index(labs[0]) == 0 and shown.index("Pasal 2\n") < shown.index(labs[2])  # judul tanpa label
    assert shown.count("[ALAMAT UNIT:") == 3
    stripped = shown
    for x in labs:
        stripped = stripped.replace(x, "")
    assert stripped == TEXT[8:118]  # hanya disisipkan
    assert cm.tokens == entries(False)[0].tokens  # anggaran sama dengan/ tanpa label (H-066)
    text, _ = render(load_prompt("v2"), "q?", [cm, c1])
    assert f"ALAMAT: {cm.address}" in text  # label rentang apa adanya
    # potongan satu unit: byte-identik dengan tanpa label
    assert c1.labels == () and c1.shown() == TEXT[87:118]
    assert render(load_prompt("v2"), "q?", [c1]) == render(load_prompt("v2"), "q?", [entries(False)[1]])
    assert entry_labels(amap, 8, 43) == ()


def test_f_verifier_tidak_berubah_oleh_prompt():
    from .verifier_fixtures import verify
    r = verify(a("Pasal 1", "ayat (1)") + " – " + a("Pasal 2"), "Perseroan berkedudukan di kota.")
    assert r.exists == "gagal"
