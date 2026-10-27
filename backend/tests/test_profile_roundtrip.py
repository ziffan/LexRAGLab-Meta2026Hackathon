"""M4.3 S1, S2, S3, S5, S7, S16, S21, S23: round-trip profil, hash potongan profil, skema tertanam, tokenizer, golden."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.chunking.model import make_setting_id
from backend.profile import export_profile, import_profile
from backend.profile.hashing import chunk_rows, clean_text_hash, corpus_hash, profile_chunk_set_hash
from backend.tests import profile_helpers as H

REPO = Path(__file__).resolve().parents[2]

GOLD_KEY_P1 = "1a0bc532b2e0296515946fd1379cf412ddd7ca89ec8153616aad88e0ab96a617"
GOLD_HASH_P1 = "81c2d2adc46f0c674c36086a59e942749aeadd28ea69010c42dcebd57971fdcb"
GOLD_IDS_P1 = [("6d0748826fa49265c0d3ef8b9eea3db3a80ed323c59ba20cb5d48b91df9e499d", "a0 a1 a2 a3"),
               ("5d9ae131daa7bf53b5be7135e86813ddb3b0d4985adbb4883dbf27200664756c", "a3 a4 a5 a6"),
               ("56e4babff70cdef0f90c47ce010de6cf381f6a6cbbe344d2bd3a3359788c144c", "a6 a7 a8 a9"),
               ("806c2c424c1e2a93985456a0e9e7b12d2a311388f878ac9a1aa9205428002aa6", "b0 b1 b2 b3"),
               ("52e927bece9c8817cca2d367e87373440bbd860ae5a5ebc41ee4bdb875969816", "b3 b4 b5")]
GOLD_KEY_PM = "aa7227957bf9702cabb53c5bea9793b0f3f8d31ed25d080b8164b032f0ccf612"
GOLD_HASH_PM = "236e277cdf96a750411d5340f0ceb1316e53c73b27a70a81a874efc1994996fe"
GOLD_IDS_PM = [("74937c23216af5e66920022dd783ca1c56fd37396d6e37a0b64740506897540d", "Café ab"),
               ("e0c157fde8346b6fa2457a1aad15902c7a79d99c2dd51a6553b11b344273ec01", "c› d")]


def exp(tmp_path, setting=H.P1, **kw):
    deps = H.make_deps(tmp_path, **kw)
    return deps, export_profile(deps, setting["family"], setting["setting_id"]).profile


def ok(deps, profile):
    return import_profile(deps, json.loads(json.dumps(profile)))


# ---------- S1 ----------
def test_s1_golden_and_roundtrip(tmp_path):
    chunker = H.FakeChunker()
    deps, prof = exp(tmp_path, chunker=chunker)
    # golden dihitung independen (hashlib) dari rumus skenario
    canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    h = lambda o: hashlib.sha256(canon(o).encode("utf-8")).hexdigest()
    key = h({"chunker": "fixed_size", "params": {"chunk_size_tokens": 4, "overlap_tokens": 1, "tokenizer": "toy-ws/1", "impl_version": "1"}})
    assert key == GOLD_KEY_P1
    ids = [(h(["d1", 0, 11, key]), "a0 a1 a2 a3"), (h(["d1", 9, 20, key]), "a3 a4 a5 a6"), (h(["d1", 18, 29, key]), "a6 a7 a8 a9"),
           (h(["d2", 0, 11, key]), "b0 b1 b2 b3"), (h(["d2", 9, 17, key]), "b3 b4 b5")]
    assert [list(p) for p in ids] == [list(p) for p in GOLD_IDS_P1]
    assert h([list(p) for p in ids]) == GOLD_HASH_P1 == prof["chunk_set_hash"]
    assert prof["corpus_hash"] == corpus_hash([H.d1, H.d2])
    assert chunker.log == [("d1", [(0, 11), (9, 20), (18, 29)]), ("d2", [(0, 11), (9, 17)])]
    chunker.log.clear()
    assert ok(deps, prof) == {"ok": True, "chunk_set_hash_matches": True}
    assert chunker.log == [("d1", [(0, 11), (9, 20), (18, 29)]), ("d2", [(0, 11), (9, 17)])]  # 5 potongan, urutan P1


def test_s1_i_hashseed_independent(tmp_path):
    code = ("import sys; from pathlib import Path; from backend.profile import export_profile; from backend.tests import profile_helpers as H;"
            "print(export_profile(H.make_deps(Path(sys.argv[1])), 'uupt', H.P1['setting_id']).profile['chunk_set_hash'])")
    outs = []
    for seed in ("1", "2"):
        r = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=REPO, capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": seed})
        assert r.returncode == 0, r.stderr
        outs.append(r.stdout.strip())
    assert outs == [GOLD_HASH_P1, GOLD_HASH_P1]


def test_s1_ii_order_independent(tmp_path):
    class Reversed(H.FakeChunker):
        def __call__(self, *a):
            return list(reversed(super().__call__(*a)))

    _, base = exp(tmp_path)
    deps, prof = exp(tmp_path, chunker=Reversed(), docs={"uupt": [H.d2, H.d1], "akta": [H.da]})
    assert prof["chunk_set_hash"] == base["chunk_set_hash"] == GOLD_HASH_P1
    assert prof["corpus_hash"] == base["corpus_hash"] and prof["clean_sha256"] == base["clean_sha256"]
    assert ok(deps, base)["ok"] is True


def test_s1_iii_same_function_as_grid_path(tmp_path):
    """Pembanding "run asal" (A20): hash profil = fungsi hash potongan yang sama atas keluaran chunker jalur grid, dan sama
    dengan nilai golden yang dihitung `hashlib` secara mandiri dari pasangan (chunk_id, teks) golden (bukan dari kode profil)."""
    chunker = H.FakeChunker()
    docs = [H.d1, H.d2]
    chunks = {d.doc_id: chunker(d, {k: v for k, v in H.P1.items() if k != "setting_id"}, None, H.TOK) for d in docs}
    via_grid = profile_chunk_set_hash(chunk_rows(docs, chunks))
    independent = hashlib.sha256(json.dumps([list(p) for p in GOLD_IDS_P1], sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":")).encode("utf-8")).hexdigest()
    exported = exp(tmp_path)[1]["chunk_set_hash"]
    assert independent == GOLD_HASH_P1
    assert via_grid == independent
    assert exported == independent


# ---------- S2 ----------
def test_s2_independent_of_active_config(tmp_path):
    deps, prof = exp(tmp_path, config_hash="a" * 64)
    other = dataclasses.replace(deps, config_hash="b" * 64)  # config aktif lain; chunker memakai setting profil
    assert prof["config_hash"] == "a" * 64
    assert ok(other, prof) == {"ok": True, "chunk_set_hash_matches": True}


# ---------- S3 ----------
def test_s3a_hash_differs_by_params(tmp_path):
    deps = H.make_deps(tmp_path)
    p1, p2 = (export_profile(deps, "uupt", s["setting_id"]).profile for s in (H.P1, H.P2))
    assert p1["setting"]["setting_id"] != p2["setting"]["setting_id"] and p1["chunk_set_hash"] != p2["chunk_set_hash"]


def test_s3b_parameter_tamper(tmp_path):
    deps, prof = exp(tmp_path)
    prof["setting"]["overlap_tokens"] = 2
    prof["setting"]["setting_id"] = make_setting_id(prof["setting"])
    assert ok(deps, prof) == {"ok": False, "chunk_set_hash_matches": False}


def test_s3c_hash_tamper(tmp_path):
    deps, prof = exp(tmp_path)
    prof["chunk_set_hash"] = ("0" if prof["chunk_set_hash"][0] != "0" else "1") + prof["chunk_set_hash"][1:]
    assert ok(deps, prof) == {"ok": False, "chunk_set_hash_matches": False}


def test_s3d_forged_corpus_same_offsets(tmp_path):
    _, prof = exp(tmp_path)
    forged_docs = [H.d1x, H.d2]
    prof["corpus_hash"], prof["clean_sha256"] = corpus_hash(forged_docs), clean_text_hash(forged_docs)
    deps = H.make_deps(tmp_path, docs={"uupt": forged_docs})
    assert ok(deps, prof) == {"ok": False, "chunk_set_hash_matches": False}  # teks a6 a7 a8 x9 beda


# ---------- S5 ----------
def test_s5a_load_order_irrelevant(tmp_path):
    _, prof = exp(tmp_path)
    deps = H.make_deps(tmp_path, docs={"uupt": [H.d2, H.d1]})
    assert corpus_hash([H.d2, H.d1]) == prof["corpus_hash"]
    assert ok(deps, prof)["ok"] is True


def test_s5b_swapped_content_rejected(tmp_path):
    from backend.api.errors import ApiError  # noqa: F401  (galat 409 dipetakan router; di sini ProfileError)
    from backend.profile import ProfileError

    _, prof = exp(tmp_path)
    deps = H.make_deps(tmp_path, docs={"uupt": [H.d1_swapped, H.d2_swapped]})
    assert corpus_hash([H.d1_swapped, H.d2_swapped]) != prof["corpus_hash"]
    with pytest.raises(ProfileError) as e:
        ok(deps, prof)
    assert e.value.kind == "hash_mismatch"


def test_s5c_other_family_does_not_affect(tmp_path):
    deps, prof = exp(tmp_path)
    changed = H.make_deps(tmp_path, docs={"uupt": [H.d1, H.d2], "akta": [H.da_p]})
    assert ok(changed, prof)["ok"] is True
    assert corpus_hash([H.d1, H.d2]) == prof["corpus_hash"]


# ---------- S7 ----------
def test_s7_embedded_schema_used_not_active(tmp_path):
    chunker = H.FakeChunker()
    deps = H.make_deps(tmp_path, chunker=chunker)  # v2 ada dan aktif; PA1 meminta v1
    res = export_profile(deps, "akta", H.PA1["setting_id"])
    prof = res.profile
    assert prof["schema"] == H.V1_BODY and prof["setting"]["schema_version"] == 1
    assert chunker.log == [("da", [(0, 15), (15, 30), (30, 45)])]
    chunker.log.clear()
    assert ok(deps, prof) == {"ok": True, "chunk_set_hash_matches": True}
    assert chunker.log == [("da", [(0, 15), (15, 30), (30, 45)])]
    # v2 aktif akan memberi hash lain
    v2 = export_profile(deps, "akta", H.PA2["setting_id"]).profile
    assert v2["chunk_set_hash"] != prof["chunk_set_hash"] and v2["schema"] == H.V2_BODY
    # v1 dihapus dari penyimpanan sebelum impor: tetap ok
    gone = H.make_deps(tmp_path, schemas={("akta", 2): H.SCHEMAS[("akta", 2)]})
    assert ok(gone, prof)["ok"] is True


# ---------- S16 ----------
def test_s16_tokenizer_differs(tmp_path):
    _, prof = exp(tmp_path)
    assert prof["tokenizer"] == {"name": "toy-ws", "version": "1"}
    other = H.make_deps(tmp_path, tokenizer=H.ToyWs2())
    assert ok(other, prof) == {"ok": False, "chunk_set_hash_matches": False}
    assert ok(H.make_deps(tmp_path), prof)["ok"] is True  # kontrol


# ---------- S21 ----------
def test_s21_handwritten_roundtrip(tmp_path):
    chunker = H.FakeChunker("1")
    deps, prof = exp(tmp_path, H.PH, chunker=chunker)
    s = prof["setting"]
    assert prof["schema"] is None and s["chunk_size_tokens"] is None and s["overlap_tokens"] is None and s["schema_version"] is None
    chunker.log.clear()
    assert ok(deps, prof) == {"ok": True, "chunk_set_hash_matches": True}
    assert chunker.log == [("d1", [(0, 14), (15, 29)]), ("d2", [(0, 17)])]  # 3 potongan
    v2 = H.make_deps(tmp_path, chunker=H.FakeChunker("2"))
    assert ok(v2, prof) == {"ok": False, "chunk_set_hash_matches": False}


# ---------- S23 ----------
def test_s23_multibyte_clean_text(tmp_path):
    chunker = H.FakeChunker()
    deps, prof = exp(tmp_path, H.PM, chunker=chunker, docs={"uupt": [H.d4]})
    assert H.d4.sha256 != H.d4.clean_sha256
    assert chunker.log == [("d4", [(0, 7), (8, 12)])]
    ck = chunker(H.d4, {k: v for k, v in H.PM.items() if k != "setting_id"}, None, H.TOK)
    assert ck[0].chunker_key == GOLD_KEY_PM
    assert [(c.chunk_id, H.d4.text[c.start:c.end]) for c in ck] == GOLD_IDS_PM
    assert prof["chunk_set_hash"] == GOLD_HASH_PM
    assert H.d4.clean_sha256 == hashlib.sha256(H.d4.text.encode("utf-8")).hexdigest() != H.d4.sha256
    assert prof["clean_sha256"] == clean_text_hash([H.d4])  # A6: hash gabungan (doc_id, clean_sha256), bukan SHA mentah
    assert prof["corpus_hash"] == corpus_hash([H.d4]) != prof["clean_sha256"]
    assert ok(deps, prof) == {"ok": True, "chunk_set_hash_matches": True}


def test_s23_wrong_normalisation_rejected(tmp_path):
    from backend.profile import ProfileError

    deps, prof = exp(tmp_path, H.PM, docs={"uupt": [H.d4]})
    bad = H.Doc("d4", "uupt", H.D4_CLEAN + "\n", H.d4.sha256, H.sha(H.D4_CLEAN + "\n"), "1")  # SHA mentah sama
    with pytest.raises(ProfileError) as e:
        ok(H.make_deps(tmp_path, docs={"uupt": [bad]}), prof)
    assert e.value.kind == "hash_mismatch" and "clean text" in e.value.message


# ---------- SHOULD-2: round-trip structure_schema dengan chunker produksi dan skema format nyata ----------
def _real_schema_deps(tmp_path, body, store_body=None):
    """Akta kecil (U_TEXT, 201 karakter) dipotong chunker PRODUKSI (`make_default_chunker` -> `chunk_document`) dengan skema A
    format nyata (`levels[].marker_pattern`, `default_chunk_level`). Hanya tokenizer `toy-ws` dan korpus yang sintetis."""
    from backend import config
    from backend.profile import make_default_chunker
    from backend.tests._chunk_util import u_doc

    doc = dataclasses.replace(u_doc(), doc_id="dk", family="akta")
    st = H.setting(family="akta", chunker="structure_schema", size=None, ov=None, sv=1)
    rec = {"family": "akta", "schema_version": 1, "body": store_body or body}
    deps = dataclasses.replace(
        H.make_deps(tmp_path, docs={"akta": [doc]}), settings=lambda fam: [st] if fam == "akta" else [],
        chunker=make_default_chunker(config.load("retrieval"), config.load("grid")), schema=lambda fam, v: rec)
    return deps, st, doc


REAL_BODY = {
    "family": "akta", "default_chunk_level": 1, "notes": None,
    "levels": [
        {"order": 1, "name": "pasal", "marker_pattern": r"^###\s+Pasal\s+\d+", "examples": ["### Pasal 1"], "parent_order": None,
         "is_chunk_unit": True},
        {"order": 2, "name": "ayat", "marker_pattern": r"^\(\d+\)", "examples": ["(1) Aaa bbb."], "parent_order": 1, "is_chunk_unit": False},
        {"order": 3, "name": "penjelasan", "marker_pattern": r"^####\s+Penjelasan Pasal \d+", "examples": ["#### Penjelasan Pasal 1"],
         "parent_order": None, "is_chunk_unit": True}]}


def test_should2_structure_schema_roundtrip_with_production_chunker(tmp_path):
    deps, st, doc = _real_schema_deps(tmp_path, REAL_BODY)
    prof = export_profile(deps, "akta", st["setting_id"]).profile
    assert prof["schema"] == REAL_BODY
    # batas dihitung tangan (docs/scenarios/M1.2.md, dokumen U): Pasal 1 [0,50) Pasal 2 [52,76); Penjelasan [78,163) [164,200)
    spans = [(0, 50), (52, 76), (78, 163), (164, 200)]
    rows = sorted(chunk_rows([doc], {"dk": deps.chunker(doc, {k: v for k, v in st.items() if k != "setting_id"}, {"family": "akta",
                                                                                                                  "schema_version": 1, "body": REAL_BODY}, H.TOK)}))
    assert [(r[1], r[2]) for r in rows] == spans and all(r[4] == doc.text[r[1]:r[2]] for r in rows)
    assert ok(deps, prof) == {"ok": True, "chunk_set_hash_matches": True}
    # skema tertanam diubah (unit potong default pindah ke level penjelasan): kunci/potongan lain -> ok:false
    other = json.loads(json.dumps(prof))
    other["schema"]["default_chunk_level"] = 3
    assert ok(deps, other) == {"ok": False, "chunk_set_hash_matches": False}
    # penyimpanan berisi skema lain: impor tetap memakai yang tertanam
    deps2, _, _ = _real_schema_deps(tmp_path, REAL_BODY, store_body={**REAL_BODY, "default_chunk_level": 3})
    assert ok(deps2, prof) == {"ok": True, "chunk_set_hash_matches": True}
