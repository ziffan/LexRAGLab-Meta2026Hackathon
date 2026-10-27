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
    assert set(d) == {"best", "baseline", "verifier", "runs"} and d["verifier"] == []
    assert tr.calls == 2
    for slot in ("best", "baseline"):
        a = d[slot]
        assert a["slot"] == slot and a["item_id"] == ITEM and a["budget_tokens"] == 2000 and a["model_profile"] == "meta"
        assert validate_instance(a["output"], ANSWER_C_SCHEMA) is None and a["context_chunk_ids"]
        assert load_answer(s.runs_dir / "answers", a["answer_id"])["output"] == a["output"]
    assert d["best"]["setting_id"] != d["baseline"]["setting_id"] and d["best"]["answer_id"] != d["baseline"]["answer_id"]
    assert [x["status"] for x in d["runs"]] == ["ok", "ok"] and all(x["kind"] == "spark_c" for x in d["runs"])
    assert all(x["prompt_version"] == "v1" and x["prompt_hash"] for x in d["runs"])
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
    assert d2["best"]["output"] == d["best"]["output"] and d2["best"]["answer_id"] == d["best"]["answer_id"]
    assert scan_runs_dir(s.runs_dir) == []
    # replay (app baru, runs/ yang sama): tanpa panggilan
    c3, tr3, _ = make(svc, tmp_path, replay=True)
    d3 = c3.post(URL, json=body(svc, live=False)).json()
    assert tr3.calls == 0 and [x["status"] for x in d3["runs"]] == ["replay", "replay"]
    assert d3["best"]["output"] == d["best"]["output"]
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
    m["profiles"]["baseten_open"] = {"provider": "baseten", "model": "x", "base_url_env": "MUSE_BASE_URL",
                                     "api_key_env": "MUSE_API_KEY", "for_reported_numbers": False, "roles": ["c"]}
    c, tr, _ = make(svc, tmp_path, model=m)
    best, _base = ids(svc)
    other_budget = next(x for x in svc.grid_settings("uupt") if x.budget_tokens != 2000 and x.chunker == "fixed_size"
                        and x.retrieval_mode == "bm25" and not x.header_b)
    cases = [
        (body(svc, item_id="tidak-ada"), 404, "not_found"),
        (body(svc, best_setting_id="0" * 64), 404, "not_found"),
        (body(svc, model_profile="nama-ngawur"), 400, "invalid_request"),
        (body(svc, model_profile="baseten_open"), 422, "validation_failed"),
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
