"""M2.2 W6: jawaban dua kolom lewat transport palsu. Tanpa jaringan sungguhan; korpus nyata, encoder tidak dipakai (bm25)."""

import pytest
from fastapi.testclient import TestClient

from backend.answer.caller import load_answer
from backend.answer.prompt import ANSWER_C_SCHEMA
from backend.api.app import Service, create_app
from backend.pipeline.grid_run import baseline_for
from backend.spark import Ledger
from backend.spark.schema_check import validate_instance
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import BASE, K, Clock, FakeTransport, Resp, body_ok, budget_cfg, env_ok, model_cfg, scan_runs_dir

URL = "/api/families/uupt/answers"
ITEM = "kontrol-K-02"
JAWAB = {"status": "jawab", "jawaban": "Direktur dapat meminta RUPS.",
         "kutipan": [{"alamat": "UU 40/2007 › Pasal 78 › ayat (2)", "teks": "x"}]}
TOLAK = {"status": "tolak", "jawaban": None, "kutipan": []}
BTC = {"status": "bukti_tidak_cukup", "jawaban": "Konteks tidak memuat syaratnya.", "kutipan": []}


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    root = tmp_path_factory.mktemp("m22api")
    s = Service(tokenizer=get_tokenizer(), runs_dir=root / "runs", encoder=FakeEncoder(), embed_cache_dir=root / "emb")
    s.pipeline()  # korpus + pipeline dihangatkan sekali, dibagi ke app tiap test (hanya baca)
    return s


def ids(svc):
    settings = svc.grid_settings("uupt")
    best = next(s for s in settings if s.chunker == "structure_handwritten" and s.retrieval_mode == "bm25"
                and s.budget_tokens == 2000 and not s.header_b)
    return best, baseline_for(settings, best, svc.cfg("grid")["baseline"])


def body(svc, **over):
    best, base = ids(svc)
    b = {"item_id": ITEM, "best_setting_id": best.setting_id, "baseline_setting_id": base.setting_id,
         "model_profile": "meta", "live": True}
    b.update(over)
    return b


def make(svc, tmp_path, script=None, *, replay=False, budget=None, default=None, model=None):
    """App baru dengan runs/ sendiri di tmp (isolasi antar test)."""
    clock = Clock()
    tr = FakeTransport(clock, script, default if default is not None else Resp(200, body_ok(JAWAB)))
    s = Service(tokenizer=svc.tokenizer, runs_dir=tmp_path / "runs", encoder=svc._encoder, embed_cache_dir=svc.embed_cache_dir)
    s._docs, s._pipeline = svc._docs, svc._pipeline
    app = create_app(s, env=env_ok(), model_config=model or model_cfg(), budget_config=budget or budget_cfg(), replay=replay,
                     spark_transport=tr.transport)
    return TestClient(app, raise_server_exceptions=False), tr, s


def test_live_two_columns_then_cache_then_replay(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    r = c.post(URL, json=body(svc))
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"best", "baseline", "verifier", "summary", "runs", "origin_runs"}
    assert d["origin_runs"] == []  # panggilan sendiri berbayar: tanpa asal
    assert isinstance(d["verifier"], list) and len(d["summary"]) == 2 and all(x["n_items"] == 1 for x in d["summary"])
    assert tr.calls == 2
    for slot in ("best", "baseline"):
        a = d[slot]
        assert a["slot"] == slot and a["item_id"] == ITEM and a["budget_tokens"] == 2000 and a["model_profile"] == "meta"
        assert validate_instance(a["output"], ANSWER_C_SCHEMA) is None and a["context_chunk_ids"]
        assert load_answer(s.runs_dir / "answers", a["answer_id"])["output"] == a["output"]
    assert d["best"]["setting_id"] != d["baseline"]["setting_id"] and d["best"]["answer_id"] != d["baseline"]["answer_id"]
    assert [x["status"] for x in d["runs"]] == ["ok", "ok"] and all(x["kind"] == "spark_c" for x in d["runs"])
    assert all(x["prompt_version"] == "v2" and x["prompt_hash"] for x in d["runs"])
    # kedua kolom: instruksi identik (awalan masukan sama), strict, tanpa tool calling
    i0, i1 = (tr.requests[k]["input"] for k in (0, 1))
    assert i0.split("<pertanyaan-")[0] == i1.split("<pertanyaan-")[0]
    assert tr.requests[0]["body"]["text"]["format"]["strict"] is True and "tools" not in tr.requests[0]["body"]
    assert tr.requests[0]["body"]["prompt_cache_key"] == tr.requests[1]["body"]["prompt_cache_key"]
    spent = Ledger(s.runs_dir).spent()
    # ulang: cache, nol panggilan, nol biaya baru
    d2 = c.post(URL, json=body(svc)).json()
    assert tr.calls == 2 and [x["status"] for x in d2["runs"]] == ["cached", "cached"]
    assert all(x["cost_usd_micros"] == 0 for x in d2["runs"]) and Ledger(s.runs_dir).spent() == spent
    # UX-03: run cache -> RunRecord panggilan asal (cache_key sama, status ok, biaya terukur) apa adanya
    assert [o["run_id"] for o in d2["origin_runs"]] == [x["run_id"] for x in d["runs"]]
    assert d2["origin_runs"] == d["runs"]
    assert [o["cache_key"] for o in d2["origin_runs"]] == [x["cache_key"] for x in d2["runs"]]
    assert d2["best"]["output"] == d["best"]["output"] and d2["best"]["answer_id"] == d["best"]["answer_id"]
    assert scan_runs_dir(s.runs_dir) == []
    # replay (app baru, runs/ yang sama): tanpa panggilan
    c3, tr3, _ = make(svc, tmp_path, replay=True)
    d3 = c3.post(URL, json=body(svc, live=False)).json()
    assert tr3.calls == 0 and [x["status"] for x in d3["runs"]] == ["replay", "replay"]
    assert d3["best"]["output"] == d["best"]["output"]
    assert d3["origin_runs"] == d["runs"] and all(o["cost_usd_micros"] is not None for o in d3["origin_runs"])
    # live=false di mode non-replay: juga hanya baca
    d4 = c.post(URL, json=body(svc, live=False)).json()
    assert tr.calls == 2 and [x["status"] for x in d4["runs"]] == ["replay", "replay"]


def test_replay_without_stored_run_is_409_and_never_calls(svc, tmp_path):
    c, tr, _ = make(svc, tmp_path, replay=True)
    r = c.post(URL, json=body(svc, live=True))  # replay + butir bukan scene_checked: live ditolak -> baca saja
    assert r.status_code == 409 and r.json()["error"]["code"] == "replay_no_stored_run" and tr.calls == 0
    r = c.post(URL, json=body(svc, live=False))
    assert r.status_code == 409 and tr.calls == 0


@pytest.mark.parametrize("out", [TOLAK, BTC])
def test_tolak_and_bukti_tidak_cukup_are_valid_200(svc, tmp_path, out):
    c, tr, _ = make(svc, tmp_path, default=Resp(200, body_ok(out)))
    r = c.post(URL, json=body(svc))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["best"]["output"]["status"] == out["status"] == d["baseline"]["output"]["status"]
    assert d["best"]["flags"] == [] and all(x["status"] == "ok" for x in d["runs"])


def test_different_status_per_column_and_flag_for_empty_citations(svc, tmp_path):
    bare = {"status": "jawab", "jawaban": "ya", "kutipan": []}
    c, tr, _ = make(svc, tmp_path, script=[Resp(200, body_ok(bare)), Resp(200, body_ok(TOLAK))])
    d = c.post(URL, json=body(svc)).json()
    assert d["best"]["output"]["status"] == "jawab" and d["best"]["flags"] == ["jawab_tanpa_kutipan"]
    assert d["baseline"]["output"]["status"] == "tolak" and d["baseline"]["flags"] == []


def test_budget_exceeded_is_402_before_network(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, budget=budget_cfg(total=1, role=1))
    r = c.post(URL, json=body(svc))
    assert r.status_code == 402 and r.json()["error"]["code"] == "budget_exceeded" and tr.calls == 0
    assert not (s.runs_dir / "answers").exists()


def test_validation_errors_are_uniform(svc, tmp_path):
    m = model_cfg()
    m["profiles"]["b_only"] = {"provider": "baseten", "model": "x", "base_url_env": "MUSE_BASE_URL",
                                     "api_key_env": "MUSE_API_KEY", "for_reported_numbers": False, "roles": ["b"]}
    c, tr, _ = make(svc, tmp_path, model=m)
    best, _base = ids(svc)
    other_budget = next(x for x in svc.grid_settings("uupt") if x.budget_tokens != 2000 and x.chunker == "fixed_size"
                        and x.retrieval_mode == "bm25" and not x.header_b)
    cases = [
        (body(svc, item_id="tidak-ada"), 404, "not_found"),
        (body(svc, best_setting_id="0" * 64), 404, "not_found"),
        (body(svc, model_profile="nama-ngawur"), 400, "invalid_request"),
        (body(svc, model_profile="b_only"), 422, "validation_failed"),
        (body(svc, baseline_setting_id=other_budget.setting_id), 422, "validation_failed"),
        (body(svc, baseline_setting_id=best.setting_id), 422, "validation_failed"),
        ({"item_id": ITEM}, 400, "invalid_request"),
    ]
    for b, st, code in cases:
        r = c.post(URL, json=b)
        assert r.status_code == st and set(r.json()) == {"error"} and r.json()["error"]["code"] == code, (b, r.text)
        assert K not in r.text and BASE not in r.text
    assert tr.calls == 0
    assert c.post("/api/families/xyz/answers", json=body(svc)).status_code == 400


def test_provider_error_maps_without_leaking(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, default=Resp(401, {"error": {"message": f"bad key {K}"}}))
    r = c.post(URL, json=body(svc))
    assert r.status_code == 502 and r.json()["error"]["code"] == "model_error"
    assert K not in r.text and BASE not in r.text and scan_runs_dir(s.runs_dir) == []
    assert not (s.runs_dir / "answers").exists()  # galat bukan AnswerRecord


def test_baseline_must_equal_baseline_for_best_in_every_axis(svc, tmp_path):
    """S1: ukuran, overlap, atau mode retrieval berbeda dari baseline_for(best) -> 422 (bukan hanya chunker)."""
    import dataclasses
    c, tr, s = make(svc, tmp_path)
    _best, base = ids(svc)
    variants = [dataclasses.replace(base, setting_id="v-size", chunk_size_tokens=base.chunk_size_tokens + 64),
                dataclasses.replace(base, setting_id="v-overlap", overlap_tokens=base.overlap_tokens + 8)]
    extra = next(x for x in svc.grid_settings("uupt") if x.chunker == "fixed_size" and x.budget_tokens == 2000
                 and not x.header_b and x.retrieval_mode != base.retrieval_mode)
    variants.append(extra)
    real = s.grid_settings
    s.grid_settings = lambda fam: [*real(fam), *variants[:2]]
    for v in variants:
        r = c.post(URL, json=body(svc, baseline_setting_id=v.setting_id))
        assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed", (v.setting_id, r.text)
    assert tr.calls == 0


def test_first_paid_answer_record_not_overwritten_by_cache_call(svc, tmp_path):
    """S2: berkas AnswerRecord mempertahankan run_id run berbayar pertama."""
    c, tr, s = make(svc, tmp_path)
    d1 = c.post(URL, json=body(svc)).json()
    d2 = c.post(URL, json=body(svc)).json()
    assert d2["best"]["run_id"] != d1["best"]["run_id"] and tr.calls == 2
    for slot in ("best", "baseline"):
        stored = load_answer(s.runs_dir / "answers", d1[slot]["answer_id"])
        assert stored["run_id"] == d1[slot]["run_id"] != d2[slot]["run_id"]


def test_m23_verifier_filled_and_record_untouched(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    d = c.post(URL, json=body(svc)).json()
    assert [v["answer_id"] for v in d["verifier"]] == [d["best"]["answer_id"], d["baseline"]["answer_id"]]
    for v in d["verifier"]:
        assert v["citation_index"] == 0 and v["exists"] in ("lulus", "gagal") and v["valid_on_date"] == "tidak_dijalankan"
        assert v["status_table_version"] is None
    assert {(x["slot"], x["model_profile"]) for x in d["summary"]} == {("best", "meta"), ("baseline", "meta")}
    for slot in ("best", "baseline"):  # verifier tidak menulis ulang AnswerRecord
        stored = load_answer(s.runs_dir / "answers", d[slot]["answer_id"])
        assert stored == d[slot] and "verifier" not in stored


def test_m23_v1_answer_records_still_replayable(svc, tmp_path, monkeypatch):
    import backend.api.routers.answers as ans_mod
    real = ans_mod.prompt_versions
    c, tr, s = make(svc, tmp_path)
    monkeypatch.setattr(ans_mod, "prompt_versions", lambda: ["v1"])
    d1 = c.post(URL, json=body(svc)).json()
    assert all(x["prompt_version"] == "v1" for x in d1["runs"])
    monkeypatch.setattr(ans_mod, "prompt_versions", real)
    calls = tr.calls
    d2 = c.post(URL, json=body(svc, live=False)).json()  # replay: v2 tak ada -> jatuh ke v1
    assert tr.calls == calls and all(x["prompt_version"] == "v1" for x in d2["runs"])
    assert d2["best"]["output"] == d1["best"]["output"] and d2["verifier"] == d1["verifier"]


def test_origin_record_only_for_matching_ok_record(svc, tmp_path):
    """UX-03: asal dibaca dari records/<run_id> (bukan salinan cache), hanya bila status ok dan cache_key sama."""
    import json as _json

    from backend.spark import store

    c, tr, s = make(svc, tmp_path)
    d = c.post(URL, json=body(svc)).json()
    run = d["runs"][0]
    key = run["cache_key"]
    assert store.origin_record(s.runs_dir, "c", key).to_dict() == run
    assert store.origin_record(s.runs_dir, "c", "0" * 64) is None  # tanpa entri cache
    rec_path = s.runs_dir / "spark" / "records" / f"{run['run_id']}.json"
    rec = _json.loads(rec_path.read_text(encoding="utf-8"))
    rec_path.write_text(_json.dumps({**rec, "status": "error"}), encoding="utf-8")
    assert store.origin_record(s.runs_dir, "c", key) is None  # record asal bukan ok
    rec_path.write_text(_json.dumps({**rec, "cache_key": "1" * 64}), encoding="utf-8")
    assert store.origin_record(s.runs_dir, "c", key) is None  # kunci tidak cocok
    rec_path.unlink()
    assert store.origin_record(s.runs_dir, "c", key) is None  # record asal hilang
