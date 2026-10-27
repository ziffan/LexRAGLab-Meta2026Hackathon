"""H-079 (I-47 opsi B): prompt B v2, `maxLength` opsional, smoke satu panggilan, berkas `rejected`. Tanpa jaringan."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import config
from backend.grid.headers import DirHeaderStore
from backend.header_b.caller import load_header, make_call, rejected_dir, run_headers, store_dir
from backend.header_b.prompt import HEADER_B_SCHEMA, header_schema, load_prompt, schema_hash, validate_schema
from backend.header_b.render import build_prefix
from backend.header_b.run import (HeaderConfigError, Prepared, find_unit, load_header_cfg, prepare, project, run_smoke,
                                  smoke_projection)
from backend.header_b.units import Unit
from backend.tokenizer import get_tokenizer

from .spark_fakes import Resp, Rig, body_ok, scan_text
from .test_header_b_core import MAXH, Tok, doc_stub, responder, setup, units

LONG = "satu dua tiga empat lima enam"  # 6 kata > MAXH (5)
V1_HASH12 = "5de81a0c2feb"  # prompt_hash v1 (40 token) yang dipakai header v1 di runs/headers


def run(rig, prompt, prefix, us, tmp_path, gran="ayat", warm=True, **kw):
    return run_headers(rig.client, prompt, prefix, us, granularity=gran, tokenizer=Tok(), headers_dir=tmp_path / "h",
                       max_header_tokens=MAXH, max_output_tokens=1000, max_consecutive_errors=3, warm_max_output_tokens=777,
                       meta={}, warm=warm, **kw)


# ---------------------------------------------------------------- prompt v2

def test_config_selects_v2_and_hash_differs_from_v1():
    hc = load_header_cfg()
    assert hc["prompt_version"] == "v2" and hc["schema_max_length_chars"] == 190  # e0f3c6b: diaktifkan setelah smoke diterima (G-35)
    v2 = load_prompt(hc["max_header_tokens"], hc["prompt_version"])
    v1 = load_prompt(hc["max_header_tokens"], "v1")
    assert v2.version == "v2" and v1.version == "v1"
    assert v2.prompt_hash != v1.prompt_hash and v2.cache_key_for("d" * 64) != v1.cache_key_for("d" * 64)
    assert v1.prompt_hash[:12] == V1_HASH12  # v1 tidak berubah (header v1 di runs/ tetap terikat ke hash ini)
    assert "{max_header_tokens}" not in v2.template and "Bab VIII (Penggabungan dkk.)" in v2.template
    assert v2.template.count("40 token") >= 2


def test_v2_examples_fit_token_limit_and_quote_corpus():
    tok = get_tokenizer()
    tpl = load_prompt(40, "v2").template
    examples = [ln.split('Header: "', 1)[1].rsplit('"', 1)[0] for ln in tpl.splitlines() if 'Header: "' in ln]
    assert len(examples) == 2 and all(tok.count(e) <= 40 for e in examples)
    corpus = (config.REPO_ROOT / "data" / "uupt" / "UU_40_2007_PERSEROAN_TERBATAS.md").read_text(encoding="utf-8")
    assert "## BAB VIII — PENGGABUNGAN, PELEBURAN, PENGAMBILALIHAN, DAN PEMISAHAN" in corpus
    assert "## BAB IX — PEMERIKSAAN TERHADAP PERSEROAN" in corpus


def test_v1_store_is_untouched_by_v2_run(tmp_path):
    rig, _default, _pf = setup(tmp_path)
    p1 = load_prompt(MAXH, "v1")
    prefix1 = build_prefix(p1, doc_stub(), Tok())
    run(rig, p1, prefix1, units(), tmp_path)
    d1 = store_dir(tmp_path / "h", "ayat", p1)
    before = {f.name: f.read_bytes() for f in d1.glob("*.json")}
    assert before
    p2 = load_prompt(MAXH, "v2")
    assert p2.prompt_hash != p1.prompt_hash
    prefix2 = build_prefix(p2, doc_stub(), Tok())
    rig2 = Rig(tmp_path / "x", default=responder(header="Header baru"))
    run(rig2, p2, prefix2, units(), tmp_path)
    d2 = store_dir(tmp_path / "h", "ayat", p2)
    assert d2 != d1 and sorted(f.name for f in d2.glob("*.json")) == sorted(before)
    assert {f.name: f.read_bytes() for f in d1.glob("*.json")} == before
    assert load_header(tmp_path / "h", "ayat", p1, "id1")["header"] == "Konteks singkat"
    assert load_header(tmp_path / "h", "ayat", p2, "id1")["header"] == "Header baru"


# ---------------------------------------------------------------- maxLength opsional

def test_maxlength_only_when_flag_is_set():
    assert "maxLength" not in header_schema(None)["properties"]["header"] and header_schema(None) == HEADER_B_SCHEMA
    assert header_schema(190)["properties"]["header"]["maxLength"] == 190
    assert "maxLength" not in HEADER_B_SCHEMA["properties"]["header"]  # konstanta modul tidak dimutasi
    assert schema_hash() == schema_hash(None) != schema_hash(190)
    validate_schema(None)
    validate_schema(190)
    for bad in (0, -1, True, "190"):
        with pytest.raises(ValueError):
            validate_schema(bad)


def test_make_call_and_request_carry_maxlength_only_with_flag(tmp_path):
    rig, prompt, prefix = setup(tmp_path)
    u = units()[0]
    off = make_call(prompt, prefix, u, Tok(), max_header_tokens=MAXH, max_output_tokens=1000, warm_max_output_tokens=777, meta={})
    on = make_call(prompt, prefix, u, Tok(), max_header_tokens=MAXH, max_output_tokens=1000, warm_max_output_tokens=777, meta={},
                   max_length_chars=190)
    assert "maxLength" not in off["schema"]["properties"]["header"] and off["schema_hash"] == schema_hash()
    assert on["schema"]["properties"]["header"]["maxLength"] == 190 and on["schema_hash"] == schema_hash(190)
    run(rig, prompt, prefix, units()[:1], tmp_path, warm=False)
    fmt = rig.tr.requests[-1]["body"]["text"]["format"]
    assert "maxLength" not in fmt["schema"]["properties"]["header"] and fmt["strict"] is True
    rig2 = Rig(tmp_path / "y", default=responder())
    run(rig2, prompt, prefix, units()[:1], tmp_path, warm=False, max_length_chars=190)
    assert rig2.tr.requests[-1]["body"]["text"]["format"]["schema"]["properties"]["header"]["maxLength"] == 190


def test_config_validation_of_new_keys(tmp_path):
    src = (config.REPO_ROOT / "config" / "header_b.toml").read_text(encoding="utf-8")
    cases = (('schema_max_length_chars = 191', True), ('schema_max_length_chars = 0', False),
             ('schema_max_length_chars = "x"', False), ('prompt_version = ""', False))
    for i, (line, ok) in enumerate(cases):
        d = tmp_path / f"c{i}"
        d.mkdir()
        new = (src.replace("schema_max_length_chars = 190", line) if line.startswith("schema")
               else src.replace('prompt_version = "v2"', line))
        assert new != src
        (d / "header_b.toml").write_text(new, encoding="utf-8", newline="\n")
        if ok:
            assert load_header_cfg(d)["schema_max_length_chars"] == 191
        else:
            with pytest.raises(HeaderConfigError):
                load_header_cfg(d)


# ---------------------------------------------------------------- smoke

def _prepared(prompt, prefix):
    return SimpleNamespace(prompt=prompt, prefix=prefix, source="ayat", units=units())


def _hc(**over):
    hc = {"max_header_tokens": MAXH, "max_output_tokens": 1000, "max_consecutive_errors": 3, "warm_max_output_tokens": 777,
          "schema_max_length_chars": None}
    hc.update(over)
    return hc


def test_find_unit_by_key_address_and_errors():
    p = _prepared(None, None)
    assert find_unit(p, "id2").key == "id2" and find_unit(p, "UU X › Pasal 1 › ayat (1)").key == "id1"
    with pytest.raises(HeaderConfigError):
        find_unit(p, "tidak ada")
    dup = SimpleNamespace(source="ayat", units=[Unit("a", "X", "t", 1, ("a",)), Unit("b", "X", "t", 1, ("b",))])
    with pytest.raises(HeaderConfigError):
        find_unit(dup, "X")


def test_smoke_is_exactly_one_call_without_warmup_and_records_run(tmp_path):
    rig, prompt, prefix = setup(tmp_path)
    out = run_smoke(rig.client, _prepared(prompt, prefix), units()[1], tokenizer=Tok(),
                    header_cfg=_hc(schema_max_length_chars=190), headers_dir=tmp_path / "h", meta={})
    assert out["status"] == "accepted" and out["error_code"] is None and out["unit"] == "id2"
    assert len(rig.tr.requests) == 1 and "pemanasan" not in rig.tr.requests[0]["input"].split("POTONGAN YANG DIMINTA")[1]
    assert "chunk_id: id2" in rig.tr.requests[0]["input"]
    assert rig.tr.requests[0]["body"]["text"]["format"]["schema"]["properties"]["header"]["maxLength"] == 190
    recs = list((rig.runs / "spark" / "records").glob("*.json"))
    assert len(recs) == 1 and json.loads(recs[0].read_text(encoding="utf-8"))["status"] == "ok"
    assert not (tmp_path / "h").exists()  # smoke tidak menyimpan header ke store


def test_smoke_status_rejected_by_api_and_semantic(tmp_path):
    err = {"error": {"message": "Invalid schema: maxLength is not permitted", "type": "invalid_request_error"}}
    rig = Rig(tmp_path, default=Resp(400, err))
    rig_, prompt, prefix = setup(tmp_path / "s")
    out = run_smoke(rig.client, _prepared(prompt, prefix), units()[0], tokenizer=Tok(),
                    header_cfg=_hc(schema_max_length_chars=190), headers_dir=tmp_path / "h", meta={})
    assert out["status"] == "rejected_by_api" and out["error_code"] == "invalid_request" and len(rig.tr.requests) == 1
    rig3 = Rig(tmp_path / "t", default=responder(header=LONG))
    out = run_smoke(rig3.client, _prepared(prompt, prefix), units()[0], tokenizer=Tok(), header_cfg=_hc(),
                    headers_dir=tmp_path / "h3", meta={})
    assert out["status"] == "accepted" and out["error_code"] == "semantic_invalid" and len(rig3.tr.requests) == 1
    assert list(rejected_dir(tmp_path / "h3", "ayat", prompt).glob("id1.*.json"))
    rig4 = Rig(tmp_path / "u", default=Resp(401, {"error": {"message": "bad key"}}))
    out = run_smoke(rig4.client, _prepared(prompt, prefix), units()[0], tokenizer=Tok(), header_cfg=_hc(),
                    headers_dir=tmp_path / "h4", meta={})
    assert out["status"] == "inconclusive" and out["error_code"] == "invalid_api_key"


def test_smoke_projection_real_unit():
    from backend.header_b.run import load_all_configs
    hc, model_cfg, _b, rcfg, gcfg = load_all_configs()
    tok = get_tokenizer()
    p = prepare("pasal", tokenizer=tok, header_cfg=hc, retrieval_cfg=rcfg, grid_cfg=gcfg)
    sm = smoke_projection(p, p.units[0], tok, hc, model_cfg)
    assert sm["units"] == 1 and sm["calls"] == 2 and sm["prompt_version"] == "v2" and sm["cost_usd_micros"]["upper_no_cache"] > 0


# ---------------------------------------------------------------- rejected

def test_rejected_saved_not_cached_not_read_by_binding(tmp_path):
    rig, prompt, prefix = setup(tmp_path, header=LONG)
    res = run(rig, prompt, prefix, units()[:1], tmp_path, warm=False)
    assert res.outcomes[0].error["code"] == "semantic_invalid"
    rd = rejected_dir(tmp_path / "h", "ayat", prompt)
    assert rd == store_dir(tmp_path / "h", "ayat", prompt) / "rejected"
    f = rd / "id1.1.json"
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["text"] == LONG and rec["tokens_local"] == 6 and rec["error_code"] == "semantic_invalid"
    assert rec["run_id"] == res.outcomes[0].run.run_id and rec["chunk_id"] == "id1" and rec["prompt_version"] == prompt.version
    assert "exceeds 5 tokens" in rec["error_message"]
    # tidak masuk cache sukses: panggilan ulang kembali ke jaringan dan menyimpan upaya ke-2
    n = len(rig.tr.requests)
    res2 = run(rig, prompt, prefix, units()[:1], tmp_path, warm=False)
    assert len(rig.tr.requests) == n + 1 and res2.outcomes[0].run.status == "error"
    assert sorted(p.name for p in rd.glob("*.json")) == ["id1.1.json", "id1.2.json"]
    assert f.read_text(encoding="utf-8") == json.dumps(rec, sort_keys=True, ensure_ascii=False, indent=1) + "\n"  # tidak ditimpa
    # tidak terbaca sebagai header
    assert load_header(tmp_path / "h", "ayat", prompt, "id1") is None
    st = DirHeaderStore(tmp_path / "h", prompt.prompt_hash, rig.runs)
    assert st.get("id1", "ayat") is None and st.get("id1.1", "ayat") is None and st.get("rejected/id1.1", "ayat") is None
    empty = st.content_hash()
    assert empty == DirHeaderStore(tmp_path / "none", prompt.prompt_hash, rig.runs).content_hash()
    # header sah di sebelahnya tetap terbaca dan rejected tidak mengubah hash isi
    rig_ok = Rig(tmp_path / "ok", default=responder())
    run(rig_ok, prompt, prefix, units()[:1], tmp_path, warm=False)
    assert st.get("id1", "ayat")["header"] == "Konteks singkat"
    assert [p.name for p in store_dir(tmp_path / "h", "ayat", prompt).glob("*.json")] == ["id1.json"]


def test_rejected_has_no_key_or_host_text(tmp_path):
    rig, prompt, prefix = setup(tmp_path, header=LONG)
    run(rig, prompt, prefix, units(), tmp_path, warm=False)
    files = list(rejected_dir(tmp_path / "h", "ayat", prompt).glob("*.json"))
    assert len(files) == 2
    for f in files:
        assert scan_text(f.read_text(encoding="utf-8")) == []
        assert set(json.loads(f.read_text(encoding="utf-8"))) == {
            "chunk_id", "chunk_id_returned", "granularity", "prompt_version", "text", "tokens_local", "error_code",
            "error_message", "run_id"}


def test_other_failures_do_not_write_rejected(tmp_path):
    rig = Rig(tmp_path, default=Resp(400, {"error": {"message": "x"}}))
    _r, prompt, prefix = setup(tmp_path / "s")
    run(rig, prompt, prefix, units()[:1], tmp_path, warm=False)
    assert not rejected_dir(tmp_path / "h", "ayat", prompt).exists()
    rig2 = Rig(tmp_path / "t", default=Resp(200, body_ok({"chunk_id": "id1"})))  # skema salah -> schema_invalid
    run(rig2, prompt, prefix, units()[:1], tmp_path, warm=False)
    assert not rejected_dir(tmp_path / "h", "ayat", prompt).exists()


def test_client_exposes_rejected_output_only_on_semantic_failure(tmp_path):
    rig, prompt, prefix = setup(tmp_path, header=LONG)
    kw = make_call(prompt, prefix, units()[0], Tok(), max_header_tokens=MAXH, max_output_tokens=1000, warm_max_output_tokens=777, meta={})
    bad = rig.client.call(**kw)
    assert bad.output is None and json.loads(bad.rejected_output) == {"chunk_id": "id1", "header": LONG}
    # W22: cache nyata di runs/spark/b/<key>.json; keluaran gagal tidak boleh masuk (asersi lama vakum: jalur spark/cache tak ada)
    assert not list((rig.runs / "spark" / "b").glob("*.json"))
    rig2, _p, _f = setup(tmp_path / "ok")
    good = rig2.client.call(**kw)
    assert good.output is not None and good.rejected_output is None
    assert len(list((rig2.runs / "spark" / "b").glob("*.json"))) == 1  # kontrol positif: jalur cache benar
    rig3 = Rig(tmp_path / "err", default=Resp(200, body_ok({"chunk_id": "id1"})))
    assert rig3.client.call(**kw).rejected_output is None


# ---------------------------------------------------------------- proyeksi v2

@pytest.mark.parametrize("source", ["pasal", "fixed_size"])
def test_projection_works_with_v2(source):
    from backend.header_b.run import load_all_configs
    hc, model_cfg, _b, rcfg, gcfg = load_all_configs()
    assert hc["prompt_version"] == "v2"
    tok = get_tokenizer()
    p = prepare(source, tokenizer=tok, header_cfg=hc, retrieval_cfg=rcfg, grid_cfg=gcfg)
    out = project(p, tok, hc, model_cfg)
    assert out["prompt_version"] == "v2" and out["prompt_hash"] == p.prompt.prompt_hash and p.prompt.prompt_hash[:12] != V1_HASH12
    assert out["units"] > 100 and out["cost_usd_micros"]["expected"] > 0
    assert out["cost_usd_micros"]["expected"] <= out["cost_usd_micros"]["upper_cached"] <= out["cost_usd_micros"]["upper_no_cache"]


def test_prepare_follows_config_prompt_version():
    from backend.header_b.run import load_all_configs
    hc, _m, _b, rcfg, gcfg = load_all_configs()
    tok = get_tokenizer()
    a = prepare("pasal", tokenizer=tok, header_cfg=hc, retrieval_cfg=rcfg, grid_cfg=gcfg)
    b = prepare("pasal", doc=a.doc, tokenizer=tok, header_cfg=dict(hc, prompt_version="v1"), retrieval_cfg=rcfg, grid_cfg=gcfg)
    assert (a.prompt.version, b.prompt.version) == ("v2", "v1") and a.prompt.prompt_hash != b.prompt.prompt_hash
    assert b.prompt.prompt_hash[:12] == V1_HASH12
