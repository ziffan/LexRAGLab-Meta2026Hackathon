"""M2.5 klien: Glimmer lokal (Chat Completions, loopback) dan Baseten Open (Responses + strict). Nol jaringan."""

import httpx2
import pytest

from backend.spark import BudgetExceeded, ConfigInvalid, SparkClient, local_server, store
from backend.spark.schema_check import validate_instance

from .m25_fakes import GLIMMER_URL, chat_body, env_m25, m25_model_cfg
from .spark_fakes import OUT_OK, SCHEMA_X, Resp, Rig, Timeout, body_ok, budget_cfg, call_args


def rig(tmp_path, profile="glimmer_local", **kw):
    return Rig(tmp_path, profile=profile, model=m25_model_cfg(), env=env_m25(), **kw)


def refuse(_tr, _req):
    raise httpx2.ConnectError("refused")


def test_glimmer_valid_output_chat_completions_record_and_cache(tmp_path):
    r = rig(tmp_path, default=Resp(200, chat_body(OUT_OK)))
    res = r.client.call(**call_args())
    assert res.output is not None and validate_instance(res.parsed, SCHEMA_X) is None
    rq = r.tr.requests[0]
    assert rq["path"].endswith("/chat/completions") and rq["method"] == "POST"
    b = rq["body"]
    assert b["response_format"]["type"] == "json_schema" and b["response_format"]["json_schema"]["strict"] is True
    assert b["reasoning_effort"] == "high" and b["max_tokens"] == 16000 and b["model"] == "meta/muse-glimmer"
    assert "tools" not in b and "tool_choice" not in b and b["messages"][0]["role"] == "user"
    assert rq["headers"].get("authorization") == "Bearer local-no-key"  # placeholder konstan, bukan dari .env
    rec = res.record
    assert (rec.provider, rec.model, rec.quantization, rec.effort, rec.kind, rec.status) == (
        "lmstudio_local", "meta/muse-glimmer", "Q4_K_M", "high", "spark_c", "ok")
    assert rec.cost_usd_micros == 0 and rec.usage_input_tokens == 900 and rec.usage_output_tokens == 1500
    assert rec.device == "local"
    res2 = r.new_client().call(**call_args())  # run ulang: cache, tanpa panggilan
    assert res2.record.status == "cached" and res2.output == res.output and r.tr.calls == 1


def test_glimmer_timeout_comes_from_profile_config(tmp_path):
    r = rig(tmp_path, default=Resp(200, chat_body(OUT_OK)))
    r.client.call(**call_args())
    assert r.tr.requests[0]["timeout"].get("read") == 900


@pytest.mark.parametrize("resp", [
    Resp(200, chat_body(None, text='{"jawaban": 1}')),   # skema salah
    Resp(200, chat_body(None, text="bukan json")),        # bukan JSON
    Resp(200, chat_body(OUT_OK, finish="length")),        # terpotong (G-26)
    Resp(200, chat_body(None, text="")),                  # kosong
])
def test_glimmer_invalid_output_is_recorded_not_used_not_cached(tmp_path, resp):
    r = rig(tmp_path, default=resp)
    res = r.client.call(**call_args())
    assert res.output is None and res.record.status == "error"
    assert res.record.error["code"] in ("schema_invalid", "incomplete")
    assert store.cache_read(r.runs, "c", res.record.cache_key) is None
    assert any(x.status == "error" for x in store.load_records(r.runs))  # dicatat
    r.new_client().call(**call_args())
    assert r.tr.calls == 2  # tidak di-cache: panggilan ulang menembak lagi


def test_glimmer_server_down_is_model_unavailable_no_retry(tmp_path):
    r = rig(tmp_path, default=refuse)
    res = r.client.call(**call_args())
    assert res.output is None and res.record.error["code"] == "model_unavailable"
    assert res.record.cost_usd_micros is None and r.tr.calls == 1
    assert "127.0.0.1" not in res.record.error["message"]


def test_glimmer_timeout_is_not_retried(tmp_path):
    r = rig(tmp_path, script=[Timeout()], default=Resp(200, chat_body(OUT_OK)))
    res = r.client.call(**call_args())
    assert res.record.error["code"] == "timeout" and r.tr.calls == 1


@pytest.mark.parametrize("url", ["http://example.com/v1", "http://10.0.0.5:8080/v1", "https://api.openai.com/v1",
                                 "http://127.0.0.1.evil.com/v1", "ftp://127.0.0.1/v1"])
def test_non_loopback_base_url_rejected_before_network(tmp_path, url):
    m = m25_model_cfg()
    m["profiles"]["glimmer_local"]["base_url"] = url
    for replay in (False, True):
        with pytest.raises(ConfigInvalid):
            SparkClient("glimmer_local", model_config=m, budget_config=budget_cfg(), env=env_m25(),
                        runs_dir=tmp_path / "r", replay=replay)


def test_glimmer_cap_c_does_not_block_local(tmp_path):
    r = rig(tmp_path, budget=budget_cfg(total=0, role=0), default=Resp(200, chat_body(OUT_OK)))
    assert r.client.call(**call_args()).output is not None  # harga 0; tidak menambah belanja Model API


def test_probe_models_ok_missing_down_and_nonloopback():
    def tr(status=200, ids=("meta/muse-glimmer",)):
        return httpx2.MockTransport(lambda req: httpx2.Response(status, json={"data": [{"id": i} for i in ids]}))

    assert local_server.probe_models(GLIMMER_URL, "meta/muse-glimmer", transport=tr()) == (True, "Available.")
    ok, msg = local_server.probe_models(GLIMMER_URL, "meta/muse-glimmer", transport=tr(ids=("other",)))
    assert not ok and "not loaded" in msg
    ok, msg = local_server.probe_models(GLIMMER_URL, "meta/muse-glimmer", transport=tr(status=500))
    assert not ok and "500" in msg

    def boom(req):
        raise httpx2.ConnectError("refused")
    ok, msg = local_server.probe_models(GLIMMER_URL, "m", transport=httpx2.MockTransport(boom))
    assert not ok and "not running" in msg
    called = []
    ok, msg = local_server.probe_models("http://example.com/v1", "m",
                                        transport=httpx2.MockTransport(lambda r: called.append(1)))
    assert not ok and "loopback" in msg and not called


def test_baseten_responses_strict_and_cost_from_usage(tmp_path):
    usage = {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 400}, "output_tokens": 500,
             "output_tokens_details": {"reasoning_tokens": 465}, "cache_write_tokens": 200}
    r = rig(tmp_path, profile="baseten_open", default=Resp(200, body_ok(OUT_OK, usage)))
    res = r.client.call(**call_args())
    rq = r.tr.requests[0]
    assert rq["path"].endswith("/responses") and rq["body"]["text"]["format"]["strict"] is True
    assert rq["body"]["max_output_tokens"] == 6000 and "tools" not in rq["body"]
    # (600*1.25M + 400*0.15M + 500*4.25M) / 1M = 2935 micro-USD, integer
    assert res.record.cost_usd_micros == 2935 and isinstance(res.record.cost_usd_micros, int)
    assert (res.record.provider, res.record.model, res.record.effort) == (
        "baseten", "meta-models/muse-spark-open-1026", "low")


def test_baseten_role_c_cap_still_applies(tmp_path):
    r = rig(tmp_path, profile="baseten_open", budget=budget_cfg(role=100), default=Resp(200, body_ok(OUT_OK)))
    with pytest.raises(BudgetExceeded):
        r.client.call(**call_args(est_input=5000, max_output_tokens=800))
    assert r.tr.calls == 0


def test_baseten_projection_uses_max_output_tokens_floor_exactly(tmp_path):
    r = rig(tmp_path, profile="baseten_open")
    # lantai 6000 menggantikan 800: (1000*1.25M + 6000*4.25M) / 1M = 26750; tanpa lantai hanya 4650
    p = r.client.project_batch([call_args(est_input=1000, max_output_tokens=800)])
    assert p.per_call_micros == [26750] and p.total_micros == 26750
    g = rig(tmp_path / "g").client.project_batch([call_args(est_input=1000, max_output_tokens=800)])
    assert g.per_call_micros == [0]  # lokal berharga 0


def test_glimmer_http_client_ignores_proxy_env(tmp_path, monkeypatch):
    import backend.spark.client as cl
    seen = []
    real = cl.httpx2.Client

    class Spy(real):  # subclass: isinstance di SDK tetap benar
        def __init__(self, *a, **kw):
            seen.append(kw)
            super().__init__(*a, **kw)

    monkeypatch.setattr(cl.httpx2, "Client", Spy)
    SparkClient("glimmer_local", model_config=m25_model_cfg(), budget_config=budget_cfg(), env=env_m25(), runs_dir=tmp_path / "r")
    assert seen and seen[0].get("trust_env") is False
