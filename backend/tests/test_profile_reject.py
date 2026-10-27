"""M4.3 S4, S6, S15, S17, S22: penolakan impor (409 hash_mismatch, 422 validation_failed), urutan cek, tanpa efek samping."""

from __future__ import annotations

import copy
import json

import pytest

from backend.chunking.model import make_setting_id
from backend.profile import ProfileError, export_profile, import_profile
from backend.profile.hashing import clean_text_hash, corpus_hash
from backend.tests import profile_helpers as H

SENTENCE = "Profile corpus hash does not match loaded corpus"


def exported(tmp_path, setting=H.P1, **kw):
    deps = H.make_deps(tmp_path, **kw)
    return export_profile(deps, setting["family"], setting["setting_id"]).profile


def rejected(deps, profile) -> ProfileError:
    with pytest.raises(ProfileError) as e:
        import_profile(deps, copy.deepcopy(profile))
    return e.value


def with_id(p):
    p["setting"]["setting_id"] = make_setting_id(p["setting"])
    return p


# ---------- S4 ----------
@pytest.mark.parametrize("name,docs", [("a", [H.d1x, H.d2]), ("b", [H.d1n, H.d2]), ("c", [H.d1]), ("d", [H.d1, H.d2, H.d3]),
                                       ("e", [H.d1x, H.d2])])
def test_s4_corpus_mismatch_409(tmp_path, name, docs):
    prof = exported(tmp_path)
    if name == "e":
        prof["chunk_set_hash"] = "f" * 64  # tetap 409, bukan ok:false
    chunker = H.FakeChunker()
    err = rejected(H.make_deps(tmp_path / "x", docs={"uupt": docs}, chunker=chunker), prof)
    assert err.kind == "hash_mismatch" and SENTENCE in err.message
    assert prof["corpus_hash"][:12] in err.message and corpus_hash(docs)[:12] in err.message
    assert "Traceback" not in err.message and chunker.calls == 0
    assert not (tmp_path / "x").exists()


# ---------- S6 ----------
def test_s6_loader_rules_differ(tmp_path):
    prof = exported(tmp_path)
    d1_v2 = H.make_doc("d1", "uupt", H.D1T, clean=H.D1T + " ", rules="2")  # SHA mentah sama, teks bersih beda
    d2_v2 = H.make_doc("d2", "uupt", H.D2T, rules="2")
    assert corpus_hash([d1_v2, d2_v2]) == prof["corpus_hash"]
    chunker = H.FakeChunker()
    err = rejected(H.make_deps(tmp_path, docs={"uupt": [d1_v2, d2_v2]}, chunker=chunker), prof)
    assert err.kind == "hash_mismatch" and "loader rules" in err.message and "clean text" in err.message
    assert SENTENCE not in err.message and chunker.calls == 0


def test_s6_i_only_clean_sha_differs(tmp_path):
    prof = exported(tmp_path)
    d1c = H.make_doc("d1", "uupt", H.D1T, clean=H.D1T + " ")  # aturan pemuat sama
    err = rejected(H.make_deps(tmp_path, docs={"uupt": [d1c, H.d2]}), prof)
    assert err.kind == "hash_mismatch" and "clean text" in err.message and "loader rules" not in err.message


def test_s6_ii_corpus_and_rules_differ(tmp_path):
    prof = exported(tmp_path)
    d1x2 = H.make_doc("d1", "uupt", H.D1T.replace("a9", "x9"), rules="2")
    d2_2 = H.make_doc("d2", "uupt", H.D2T, rules="2")
    err = rejected(H.make_deps(tmp_path, docs={"uupt": [d1x2, d2_2]}), prof)
    assert err.kind == "hash_mismatch" and SENTENCE in err.message and "loader rules" in err.message


# ---------- S15 ----------
def _del(k):
    return lambda p: p.pop(k)


def _set(path, value):
    def f(p):
        t = p
        for k in path[:-1]:
            t = t[k]
        t[path[-1]] = value
    return f


def _fix(f):
    return lambda p: with_id((f(p), p)[1])


def _id_char(p):
    sid = p["setting"]["setting_id"]
    p["setting"]["setting_id"] = ("0" if sid[0] != "0" else "1") + sid[1:]


MUTATIONS = {
    "a": ("P1", _del("corpus_hash"), "corpus_hash"),
    "b": ("P1", _set(["packing"], "truncate_all"), "packing"),
    "c": ("P1", _set(["family"], "pt"), "family"),
    "d": ("P1", _set(["profile_version"], "2"), "profile_version"),
    "e": ("P1", _fix(_set(["setting", "retrieval_mode"], "semantic")), "retrieval_mode"),
    "f": ("P1", _id_char, "setting_id"),
    "g": ("P1", _set(["held_out"], None), "held_out"),
    "h": ("PA1", _set(["held_out"], {"n_items": 0, "by_origin": {}, "mean_span_recall": None, "mean_token_precision": None,
                                      "fully_covered": {"covered": 0, "total": 0}}), "held_out"),
    "i": ("PA1", _set(["schema"], None), "schema"),
    "j": ("P1", _set(["schema"], {"x": 1}), "schema"),
    "k": ("P1", _fix(_set(["setting", "chunk_size_tokens"], None)), "chunk_size_tokens"),
    "m1": ("PH", _fix(_set(["setting", "chunk_size_tokens"], 4)), "chunk_size_tokens"),
    "m2": ("PH", _set(["schema"], {"x": 1}), "schema"),
}


@pytest.mark.parametrize("key", list(MUTATIONS))
def test_s15_malformed_422_before_hash_check(tmp_path, key):
    which, mutate, field = MUTATIONS[key]
    prof = exported(tmp_path, {"P1": H.P1, "PA1": H.PA1, "PH": H.PH}[which])
    mutate(prof)
    chunker = H.FakeChunker()
    err = rejected(H.make_deps(tmp_path, chunker=chunker), prof)
    assert err.kind == "validation_failed" and field in err.message and chunker.calls == 0


def test_s15_l_malformed_and_forged_corpus_still_422(tmp_path):
    prof = exported(tmp_path)
    del prof["clean_sha256"]
    prof["corpus_hash"] = "e" * 64
    assert rejected(H.make_deps(tmp_path), prof).kind == "validation_failed"


def test_s15_non_object_and_extra_field(tmp_path):
    prof = exported(tmp_path)
    prof["extra"] = 1
    assert rejected(H.make_deps(tmp_path), prof).kind == "validation_failed"
    assert rejected(H.make_deps(tmp_path), []).kind == "validation_failed"


# ---------- S17 ----------
def test_s17_import_has_no_side_effects(tmp_path):
    prof = exported(tmp_path / "src")
    work = tmp_path / "work"
    (work / "runs").mkdir(parents=True)
    (work / "runs" / "keep.json").write_text("{}", encoding="utf-8")
    deps = H.make_deps(work)  # profiles_dir = work/profiles
    before = H.tree(work)
    bad_corpus = copy.deepcopy(prof)
    bad_corpus["corpus_hash"] = "a" * 64
    bad_hash = copy.deepcopy(prof)
    bad_hash["chunk_set_hash"] = "b" * 64
    assert import_profile(deps, copy.deepcopy(prof)) == {"ok": True, "chunk_set_hash_matches": True}
    assert rejected(deps, bad_corpus).kind == "hash_mismatch"
    assert import_profile(deps, bad_hash) == {"ok": False, "chunk_set_hash_matches": False}
    assert H.tree(work) == before and not (work / "profiles").exists()
    assert "a0 a1" not in json.dumps(import_profile(deps, copy.deepcopy(prof)))


# ---------- S22 ----------
@pytest.mark.parametrize("docs", ["a", "b", "c"])
def test_s22_akta_corpus_rejected(tmp_path, docs):
    prof = exported(tmp_path, H.PA1)
    mapping = {"a": [H.da_p], "b": [H.make_doc("da", "akta", H.DA_T, clean=H.DA_T + " ", rules="2")], "c": [H.da, H.da2]}
    chunker = H.FakeChunker()
    deps = H.make_deps(tmp_path / "x", docs={"akta": mapping[docs]}, chunker=chunker)
    err = rejected(deps, prof)
    assert err.kind == "hash_mismatch" and chunker.calls == 0 and not (tmp_path / "x").exists()
    if docs == "b":
        assert "loader rules" in err.message and "clean text" in err.message
    else:
        assert SENTENCE in err.message
    # kontrol
    assert import_profile(H.make_deps(tmp_path), copy.deepcopy(prof)) == {"ok": True, "chunk_set_hash_matches": True}
    assert clean_text_hash([H.da]) == prof["clean_sha256"]
