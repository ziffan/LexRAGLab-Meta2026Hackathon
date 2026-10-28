"""H-101 bagian 1 (skenario M3.2-open-weight-B S1-S5, S11 (k)): jalur store pembanding, byte-identik utama, kenari, identitas
store, validator tetap, validasi config. Tanpa Model API, tanpa jaringan, data sintetis."""

import copy
import json
import os

import pytest

from backend.grid.headers import DirHeaderStore, header_store_dir
from backend.header_b import caller
from backend.header_b import compare as cmp
from backend.header_b.caller import rejected_dir, store_dir
from backend.header_b.compare_store import (CompareError, MainIdentityChanged, assert_main_identity, build_identity,
                                            check_forbidden_profile_keys, check_identity, check_no_overlap, compare_store_dir,
                                            comparison_profile, read_identity, snapshot_main, validate_compare_cfg, write_identity)
from backend.spark.errors import ConfigInvalid

from .h101_helpers import (PROMPT12, Tok, hc_b, make_prepared, model_b, prompt_a, put_header, rig_for, words)
from .h101_run import go
from .spark_fakes import Resp

H = "a" * 64  # prompt_hash fixture ("aaaaaaaaaaaa" = prompt12)
H_UUPT = "8ee8a76ca6f1938e3b378d40d5f84ef17824b7c5c4b50b9dd3cdd3648dcae120"
H_AKTA = "3840bdf61d794a2fc2689dfcedb5157ff6a5d658de26b1975a86591ecbe3889b"
H_CMP = "a4b7d17b3c40be0515e9dc0662ef721a659246530c2eaa2f115ccb3a28087d9c"


def main_fixture(R):
    for cid, t in (("CH-U1", "Pasal 1 Ketentuan Umum"), ("CH-U2", "Pasal 2 Pendirian"), ("CH-U3", "Pasal 3 Modal")):
        put_header(R / "headers", "pasal", cid, t)
    for cid, t in (("CH-A1", "Akta 91 Pasal 1 Nama"), ("CH-A2", "Akta 91 Pasal 2 Tempat")):
        put_header(R / "headers" / "akta", "pasal", cid, t)
    (R / "grid").mkdir(parents=True)
    (R / "grid" / "K0.json").write_text('{"key":"K0"}\n', encoding="utf-8")
    (R / "schemas" / "uupt").mkdir(parents=True)
    (R / "schemas" / "uupt" / "v1.json").write_text('{"v":1}\n', encoding="utf-8")


# ------------------------------------------------------------------------------------------------ S1
def test_s1a_paths_per_profile_and_family(tmp_path):
    R = tmp_path / "runs"
    assert compare_store_dir(R, "baseten_open", "uupt") == R / "headers_compare" / "baseten_open"
    assert compare_store_dir(R, "baseten_open", "akta") == R / "headers_compare" / "baseten_open" / "akta"
    assert compare_store_dir(R, "glimmer_local", "uupt") == R / "headers_compare" / "glimmer_local"
    assert compare_store_dir(R, "glimmer_local", "akta") == R / "headers_compare" / "glimmer_local" / "akta"
    p = prompt_a()
    d = compare_store_dir(R, "baseten_open")
    assert store_dir(d, "pasal", p) == d / "pasal" / PROMPT12
    assert rejected_dir(d, "pasal", p) == d / "pasal" / PROMPT12 / "rejected"
    assert d.parent.name == "headers_compare" and "headers" not in d.relative_to(R).parts[:1]  # bukan di bawah runs/headers


@pytest.mark.parametrize("name", ["xx", "meta", "c_only", "openrouter_dev", "a/b", "a\\b", "..", "a..b", "", " "])
def test_s1b_profile_names_rejected_before_network(name):
    with pytest.raises(CompareError) as ei:
        comparison_profile(model_b(), name)
    assert ei.value.code == "config_invalid"


def test_s1b_valid_profiles_and_missing_roles_key():
    m = model_b()
    assert comparison_profile(m, "baseten_open")["provider"] == "baseten"
    assert comparison_profile(m, "glimmer_local")["provider"] == "lmstudio_local"
    assert "roles" not in m["profiles"]["openrouter_dev"] and "roles" not in m["profiles"]["meta"]  # P18: bukan "semua peran"
    m["profiles"]["baseten_open"]["roles"] = "b"  # bukan daftar
    with pytest.raises(CompareError):
        comparison_profile(m, "baseten_open")


def test_s1c_overlap_by_path_components_not_string_prefix(tmp_path):
    R = tmp_path / "runs"
    main = R / "headers"
    main.mkdir(parents=True)
    for bad in (main, main / "compare" / "x", main / "akta"):
        with pytest.raises(CompareError) as ei:
            check_no_overlap(bad, main, casefold=False)
        assert ei.value.code == "compare_store_overlaps_main"
    check_no_overlap(R / "headers_compare" / "x", main, casefold=False)  # awalan teks sama, bukan anak direktori
    with pytest.raises(CompareError):
        check_no_overlap(R, main, casefold=False)  # membungkus store utama


def test_s1c2_normalisation_casefold_and_symlink(tmp_path):
    R = tmp_path / "runs"
    main = R / "headers"
    main.mkdir(parents=True)
    with pytest.raises(CompareError):
        check_no_overlap(R / "headers" / ".." / "headers" / "x", main, casefold=False)
    check_no_overlap(R / "headers_compare" / ".." / "headers_compare" / "x", main, casefold=False)
    # huruf besar/kecil: penentu disuntikkan; direktori `R2/headers` sengaja tidak dibuat (Windows menormalkan huruf yang ada)
    R2 = tmp_path / "other"
    R2.mkdir()
    with pytest.raises(CompareError):
        check_no_overlap(R2 / "HEADERS" / "x", R2 / "headers", casefold=True)
    check_no_overlap(R2 / "HEADERS" / "x", R2 / "headers", casefold=False)
    link = R / "headers_compare" / "y"
    link.parent.mkdir()
    try:
        os.symlink(main, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not permitted on this system")
    with pytest.raises(CompareError) as ei:
        check_no_overlap(link, main, casefold=False)
    assert ei.value.code == "compare_store_overlaps_main"
    with pytest.raises(CompareError):
        compare_store_dir(R, "y", "akta", casefold=False)


# ------------------------------------------------------------------------------------------------ S2 / S3
def run_comparison_writes(tmp_path):
    """Run B pembanding Baseten (UU PT + akta) dan Glimmer (UU PT) ke store terpisah; mengembalikan (R, rig_bt)."""
    bt = rig_for(tmp_path, "baseten_open", {"CH-U1": ["Pasal 1 definisi"], "CH-U2": ["Pasal 2 pendirian PT"],
                                            "CH-U3": [words(41), "Pasal 3 modal dasar"]})
    R = bt.runs
    s = go(bt, make_prepared(3), compare_store_dir(R, "baseten_open", "uupt"))
    assert s["stopped"] is None and not s["failed"]
    ak = make_prepared(2, doc_id="akta-91", prefix="CH-A", sha="d")
    assert go(bt, ak, compare_store_dir(R, "baseten_open", "akta"))["stored"] == 2
    gl = rig_for(tmp_path, "glimmer_local")
    assert go(gl, make_prepared(3), compare_store_dir(R, "glimmer_local", "uupt"), profile="glimmer_local")["stored"] == 3
    return R, bt


def test_s2_main_stores_byte_identical_after_comparison_runs(tmp_path):
    R = tmp_path / "runs"
    main_fixture(R)
    assert DirHeaderStore(header_store_dir(R, "uupt"), H, R).content_hash() == H_UUPT
    assert DirHeaderStore(header_store_dir(R, "akta"), H, R).content_hash() == H_AKTA
    before = snapshot_main(R, H)
    R2, _ = run_comparison_writes(tmp_path)
    assert R2 == R
    after = snapshot_main(R, H)
    assert before == after
    assert_main_identity(before, after)  # daftar beda kosong -> tidak melempar
    cdir = compare_store_dir(R, "baseten_open", "uupt")
    assert DirHeaderStore(cdir, H, R).content_hash() == H_CMP != H_UUPT  # teks beda, chunk_id sama
    rej = list((cdir / "pasal" / PROMPT12 / "rejected").glob("CH-U3.*.json"))
    assert [p.name for p in rej] == ["CH-U3.1.json"]  # rejected/ tidak ikut hash (glob tingkat atas tanpa rekursi)
    assert (R / "headers_compare" / "glimmer_local" / "pasal" / PROMPT12 / "CH-U1.json").is_file()
    assert (R / "headers_compare" / "baseten_open" / "akta" / "pasal" / PROMPT12 / "CH-A1.json").is_file()


def test_s3_canary_fails_for_each_sabotage_with_exact_item_set(tmp_path):
    R = tmp_path / "runs"
    main_fixture(R)
    base = snapshot_main(R, H)

    def changed_by(action):
        action()
        with pytest.raises(MainIdentityChanged) as ei:
            assert_main_identity(base, snapshot_main(R, H))
        assert ei.value.code == "main_identity_changed"
        return set(ei.value.items)

    def undo(p):
        p.unlink()

    p1 = R / "headers" / "pasal" / PROMPT12 / "CH-U9.json"
    assert changed_by(lambda: put_header(R / "headers", "pasal", "CH-U9", "Pasal 9 Sisipan")) == {"uupt_store_hash", "headers_listing"}
    assert DirHeaderStore(header_store_dir(R, "uupt"), H, R).content_hash() == "47e9435b447eeab76c5215cd90088e92691ce95005766ce56ee68b0e18f8c893"
    assert DirHeaderStore(header_store_dir(R, "akta"), H, R).content_hash() == H_AKTA  # akta tak ikut
    undo(p1)
    assert snapshot_main(R, H) == base
    assert changed_by(lambda: put_header(R / "headers" / "akta", "pasal", "CH-A9", "Akta 91 Pasal 9")) == {"akta_store_hash", "headers_listing"}
    assert DirHeaderStore(header_store_dir(R, "uupt"), H, R).content_hash() == H_UUPT  # subdir akta tak di-glob hash UU PT
    (R / "headers" / "akta" / "pasal" / PROMPT12 / "CH-A9.json").unlink()
    assert changed_by(lambda: (R / "grid" / "zz.json").write_text("{}\n", encoding="utf-8")) == {"grid_listing"}
    (R / "grid" / "zz.json").unlink()
    assert changed_by(lambda: (R / "schemas" / "uupt" / "v1.json").write_text('{"v":2}\n', encoding="utf-8")) == {"schemas_listing"}


def test_s3_extras_are_part_of_the_snapshot(tmp_path):
    R = tmp_path / "runs"
    main_fixture(R)
    box = {"v": "h1"}
    b = snapshot_main(R, H, extras={"config_hash_uupt": lambda: box["v"]})
    box["v"] = "h2"
    with pytest.raises(MainIdentityChanged) as ei:
        assert_main_identity(b, snapshot_main(R, H, extras={"config_hash_uupt": lambda: box["v"]}))
    assert ei.value.items == {"config_hash_uupt"}


# ------------------------------------------------------------------------------------------------ S4
def ident(m, profile="glimmer_local", prompt_hash="H1"):
    return build_identity(profile, m["profiles"][profile], m, prompt_hash=prompt_hash, max_header_tokens=40,
                          schema_max_length_chars=190)


def test_s4_identity_created_once_and_rejects_changes(tmp_path):
    m = model_b()
    root = tmp_path / "runs" / "headers_compare" / "glimmer_local"
    i1 = ident(m)
    assert i1 == {"profile": "glimmer_local", "provider": "lmstudio_local", "model": "meta/muse-glimmer", "quantization": "Q4_K_M",
                  "effort": "high", "prompt_hash": "H1", "max_header_tokens": 40, "schema_max_length_chars": 190}
    assert check_identity(root, i1) is False  # belum ada
    assert write_identity(root, i1) is True
    raw = (root / "identity.json").read_bytes()
    assert json.loads(raw) == i1
    assert check_identity(root, i1) is True and write_identity(root, i1) is False
    assert (root / "identity.json").read_bytes() == raw  # tidak ditulis ulang
    changes = [("effort", lambda c: c["profiles"]["glimmer_local"].__setitem__("reasoning_effort", "medium"), "H1"),
               ("quantization", lambda c: c["profiles"]["glimmer_local"].__setitem__("quantization", "Q8_0"), "H1"),
               ("model", lambda c: c["profiles"]["glimmer_local"].__setitem__("model", "meta/muse-glimmer-2"), "H1"),
               ("prompt_hash", lambda c: None, "H2")]
    for field, mut, ph in changes:
        c = copy.deepcopy(m)
        mut(c)
        with pytest.raises(CompareError) as ei:
            check_identity(root, ident(c, prompt_hash=ph))
        assert ei.value.code == "compare_identity_mismatch" and field in str(ei.value)
        assert "http" not in str(ei.value) and "KEY" not in str(ei.value)
    assert (root / "identity.json").read_bytes() == raw


def test_s4d_invalid_identity_file_not_overwritten(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    for body in (b"not json", b"[1, 2]"):
        (root / "identity.json").write_bytes(body)
        with pytest.raises(CompareError) as ei:
            read_identity(root)
        assert ei.value.code == "compare_identity_invalid"
        with pytest.raises(CompareError):
            check_identity(root, {"profile": "x"})
        assert write_identity(root, {"profile": "x"}) is False
        assert (root / "identity.json").read_bytes() == body


def test_s4e_floor_change_is_not_identity_but_model_id_is(tmp_path):
    m = model_b()
    root = tmp_path / "bt"
    write_identity(root, ident(m, "baseten_open"))
    m["profiles"]["baseten_open"]["max_output_tokens"] = 8000
    assert check_identity(root, ident(m, "baseten_open")) is True
    m["profiles"]["baseten_open"]["model"] = "meta-models/other"
    with pytest.raises(CompareError) as ei:
        check_identity(root, ident(m, "baseten_open"))
    assert ei.value.code == "compare_identity_mismatch" and "model" in str(ei.value)


def test_s4f_new_profile_is_the_official_way_out(tmp_path):
    m = model_b()
    R = tmp_path / "runs"
    write_identity(R / "headers_compare" / "glimmer_local", ident(m))
    m["profiles"]["glimmer_local_q8"] = {**m["profiles"]["glimmer_local"], "quantization": "Q8_0"}
    m["pricing"]["glimmer_local_q8"] = dict(m["pricing"]["glimmer_local"])
    prof = comparison_profile(m, "glimmer_local_q8")
    i8 = build_identity("glimmer_local_q8", prof, m, prompt_hash="H1", max_header_tokens=40, schema_max_length_chars=190)
    root8 = R / "headers_compare" / "glimmer_local_q8"
    assert check_identity(root8, i8) is False and write_identity(root8, i8) is True
    assert json.loads((R / "headers_compare" / "glimmer_local" / "identity.json").read_text())["quantization"] == "Q4_K_M"


class SpyBlock(Exception):
    pass


def listing(root):
    """Berkas store/identitas (tanpa laporan run di `runs/`)."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "runs" not in p.relative_to(root).parts)


def cli_args(profile="glimmer_local", *extra):
    return ["--model-profile", profile, "--family", "uupt", "--sources", "pasal", *extra]


def cli_run(tmp_path, rig, argv, *, model=None, prepared=None, **kw):
    fake = lambda ids, sources, **k: {"uupt-x": {"pasal": prepared or make_prepared(3)}}  # noqa: E731
    return cmp.main(argv, env=rig.env, model_config=model or rig.model, budget_config=rig.budget, header_config=hc_b(),
                    runs_dir=rig.runs, transport=rig.tr.transport, out=lambda s: None, tokenizer=Tok(), prepare_fn=fake,
                    probe=lambda u, m: (True, "ok"), **kw)


def test_s4c_cli_rejects_identity_mismatch_before_network_and_writes_nothing(tmp_path):
    rig = rig_for(tmp_path, "glimmer_local")
    assert cli_run(tmp_path, rig, cli_args("glimmer_local", "--max-units", "1")) == 0
    n_requests = rig.tr.calls
    root = rig.runs / "headers_compare" / "glimmer_local"
    files = listing(root)
    assert "identity.json" in files and n_requests == 1
    for mut in (lambda m: m["profiles"]["glimmer_local"].__setitem__("reasoning_effort", "medium"),
                lambda m: m["profiles"]["glimmer_local"].__setitem__("quantization", "Q8_0")):
        m = model_b()
        mut(m)
        rig2 = rig_for(tmp_path, "glimmer_local", model=m)
        assert cli_run(tmp_path, rig2, cli_args("glimmer_local"), model=m) == 2
        assert rig2.tr.calls == 0  # spy: nol request
    after = listing(root)
    assert after == files  # tidak ada berkas header baru


# ------------------------------------------------------------------------------------------------ S5
def one_unit(tmp_path, header, profile="baseten_open"):
    rig = rig_for(tmp_path, profile, {"CH-U1": [header]})
    d = compare_store_dir(rig.runs, profile)
    s = go(rig, make_prepared(1), d, max_attempts=1)
    return rig, d, s


@pytest.mark.parametrize("profile", ["baseten_open", "glimmer_local"])
def test_s5a_190_chars_40_tokens_accepted(tmp_path, profile):
    h = words(40, 151)
    assert len(h) == 190 and Tok().count(h) == 40
    _, d, s = one_unit(tmp_path, h, profile)
    assert s["stored"] == 1 and (d / "pasal" / PROMPT12 / "CH-U1.json").is_file()


def test_s5b_41_tokens_rejected_and_kept_in_rejected(tmp_path):
    rig, d, s = one_unit(tmp_path, words(41))
    assert s["stored"] == 0 and s["failed"] == {"uupt-x/pasal": ["CH-U1"]}
    assert not (d / "pasal" / PROMPT12 / "CH-U1.json").exists()
    rec = json.loads((d / "pasal" / PROMPT12 / "rejected" / "CH-U1.1.json").read_text(encoding="utf-8"))
    assert rec["tokens_local"] == 41 and rec["error_code"] == "semantic_invalid" and "exceeds 40 tokens" in rec["error_message"]
    assert not (rig.runs / "headers").exists()  # store utama tidak disentuh


def test_s5c_191_chars_is_schema_invalid_not_semantic_and_not_in_rejected(tmp_path):
    h = words(40, 152)
    assert len(h) == 191
    rig, d, s = one_unit(tmp_path, h)
    assert s["stored"] == 0 and not (d / "pasal" / PROMPT12 / "rejected").exists()
    from backend.spark import store
    errs = [r.error["code"] for r in store.load_records(rig.runs) if r.status == "error"]
    assert errs == ["schema_invalid"]


@pytest.mark.parametrize("header", ["", "   "])
def test_s5d_empty_or_blank_header_rejected(tmp_path, header):
    _, d, s = one_unit(tmp_path, header)
    assert s["stored"] == 0 and not (d / "pasal" / PROMPT12 / "CH-U1.json").exists()


def test_s5e_wrong_chunk_id_rejected(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", {"CH-U1": ['RAW:{"chunk_id": "CH-ZZ", "header": "Header sah"}']})
    d = compare_store_dir(rig.runs, "baseten_open")
    s = go(rig, make_prepared(1), d, max_attempts=1)
    assert s["stored"] == 0 and not (d / "pasal" / PROMPT12 / "CH-U1.json").exists()


def test_s5f_same_limits_reach_validator_and_schema_for_both_profiles(tmp_path, monkeypatch):
    seen = []
    orig = caller.make_validator

    def spy(unit, tokenizer, max_header_tokens):
        seen.append(max_header_tokens)
        return orig(unit, tokenizer, max_header_tokens)

    monkeypatch.setattr(caller, "make_validator", spy)
    for profile in ("baseten_open", "glimmer_local"):
        rig = rig_for(tmp_path / profile, profile)
        go(rig, make_prepared(1), compare_store_dir(rig.runs, profile), profile=profile, max_attempts=1)
        body = rig.tr.requests[-1]["body"]
        fmt = body["text"]["format"]["schema"] if "text" in body else body["response_format"]["json_schema"]["schema"]
        assert fmt["properties"]["header"]["maxLength"] == 190
    assert set(seen) == {40}


def test_s5f_profile_cannot_loosen_validator_but_unknown_keys_are_ignored():
    check_forbidden_profile_keys(model_b())  # kontrol: profil yang ada tetap termuat
    for key in ("max_header_tokens", "schema_max_length_chars"):
        m = model_b()
        m["profiles"]["baseten_open"][key] = 99
        with pytest.raises(ConfigInvalid):
            check_forbidden_profile_keys(m)
    m = model_b()
    m["profiles"]["baseten_open"]["kunci_asing"] = 1  # kunci tak dikenal lain tetap diabaikan
    check_forbidden_profile_keys(m)
    from backend import config
    check_forbidden_profile_keys(config.load("model"))  # config/model nyata


# ------------------------------------------------------------------------------------------------ S11 (k)
@pytest.mark.parametrize("bad", [0, -1, True, "8", 8.0])
def test_s11k_max_attempts_must_be_integer_at_least_one(bad):
    hc = hc_b(max_attempts={"baseten_open": bad})
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg(hc, model_b())


def test_s11k_unknown_profile_and_valid_values():
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg(hc_b(max_attempts={"tidak_ada": 3}), model_b())
    for ok in (1, 8):
        validate_compare_cfg(hc_b(max_attempts={"baseten_open": ok}), model_b())
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg(hc_b(projection={"doc_rpm": 150, "glimmer_local": {"prefill_tokens_per_s": 0, "base_ms": 1,
                                                                                "output_tokens_per_10s": 1}}), model_b())
    with pytest.raises(ConfigInvalid):
        validate_compare_cfg(hc_b(projection={"doc_rpm": 150, "nope": {"prefill_tokens_per_s": 1, "base_ms": 1,
                                                                       "output_tokens_per_10s": 1}}), model_b())


def test_s11k_real_config_is_valid_and_carries_the_pins():
    from backend import config
    from backend.header_b.compare_store import max_attempts_for, time_params_for
    hc, m = config.load("header_b"), config.load("model")
    validate_compare_cfg(hc, m)
    assert (max_attempts_for(hc, "baseten_open"), max_attempts_for(hc, "glimmer_local")) == (8, 3)
    assert time_params_for(hc, "glimmer_local") == {"prefill_tokens_per_s": 650, "base_ms": 4800, "output_tokens_per_10s": 237}
    assert time_params_for(hc, "baseten_open") is None
    for p in ("baseten_open", "glimmer_local"):
        assert m["profiles"][p]["roles"] == ["c", "a", "b"]
        comparison_profile(m, p)
    assert m["profiles"]["baseten_open"]["max_output_tokens"] == 6000 and m["profiles"]["glimmer_local"]["max_output_tokens"] == 16000
