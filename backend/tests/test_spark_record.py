"""M0.1 S32-S35, S37, S38: RunRecord lengkap, bentuk request Responses API, effort, gerbang H-057,
GET /api/runs, pra-validasi skema strict."""

import copy
from dataclasses import fields
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.spark import (
    NotReportable,
    RunRecord,
    require_reportable,
    store,
)
from backend.tests.spark_fakes import (
    K2,
    SCHEMA_X,
    Clock,
    K,
    Resp,
    Rig,
    body_ok,
    budget_cfg,
    call_args,
    env_ok,
    model_cfg,
    scan_text,
    synth,
)

T0 = datetime(2026, 10, 27, 10, 0, 0, tzinfo=UTC).timestamp()


def test_S32_run_record_all_fields(tmp_path):
    rig = Rig(tmp_path, clock=Clock(T0), default=Resp(200, body_ok(), advance=2.5))
    res = rig.client.call(**call_args(0))
    r = res.record
    assert r.run_id and r.kind == "spark_c" and r.created_at == "2026-10-27T10:00:00Z"
    assert r.cache_key and K not in r.cache_key
    assert (r.corpus_hash, r.clean_sha256, r.loader_rules_version) == ("CH1", "CS1", "LR1")
    assert r.config_hash and K not in r.config_hash
    assert (r.prompt_version, r.prompt_hash) == ("c-v1", "PH1")
    assert r.model == "muse-spark-1.3-contributor" and r.effort == "low"
    assert r.tokenizer == {"name": "tok-fake", "version": "0"} and r.embedder is None and r.packing is None
    assert (r.usage_input_tokens, r.usage_cached_tokens, r.usage_output_tokens) == (3247, 0, 445)
    assert r.cost_usd_micros == 414 and type(r.cost_usd_micros) is int
    assert r.latency_ms == 2500 and type(r.latency_ms) is int
    assert (r.host, r.device, r.provider, r.quantization) == ("authoritative", "remote", "meta", None)
    assert r.status == "ok" and r.error is None and r.projected_cost_usd_micros is None
    assert {f.name for f in fields(RunRecord)} == set(r.to_dict())
    # cache_key = kunci tujuh komponen (T8)
    assert r.cache_key == store.cache_key_for("meta", "muse-spark-1.3-contributor", None, "low", "PH1", "SH1",
                                               store.sha256_hex(call_args(0)["input"]))
    # round-trip dari disk
    assert store.load_records(rig.runs) == [r]
    # run_id berbeda antar panggilan
    assert rig.client.call(**call_args(1)).record.run_id != r.run_id


def test_S32_config_hash_tracks_prices_not_keys(tmp_path):
    base = Rig(tmp_path / "a").client.call(**call_args(0)).record.config_hash
    other_key = Rig(tmp_path / "b", env=env_ok(**{"MUSE_API_KEY": K2})).client.call(**call_args(0)).record.config_hash
    m = model_cfg()
    m["pricing"]["meta"]["input_per_mtok_micros"] = 200000
    priced = Rig(tmp_path / "c", model=m).client.call(**call_args(0)).record.config_hash
    assert base == other_key and base != priced


def test_S32_openrouter_provider_and_model(tmp_path):
    r = Rig(tmp_path, profile="openrouter_dev").client.call(**call_args(0)).record
    assert r.provider == "openrouter" and r.model == "meta/muse-spark-1.3-contributor" and r.cost_usd_micros == 414


@pytest.mark.parametrize("profile,model", [("meta", "muse-spark-1.3-contributor"),
                                           ("openrouter_dev", "meta/muse-spark-1.3-contributor")])
def test_S33_request_shape_responses_api_strict(tmp_path, profile, model):
    rig = Rig(tmp_path, profile=profile)
    rig.client.call(**call_args(0, max_output_tokens=800))
    q = rig.tr.requests[0]
    b = q["body"]
    assert q["method"] == "POST" and q["path"].endswith("/responses") and "chat/completions" not in q["path"]
    assert q["headers"]["authorization"] == "Bearer " + (K if profile == "meta" else K2)
    assert b["model"] == model and b["reasoning"]["effort"] == "low"
    fmt = b["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["schema"] == SCHEMA_X
    assert fmt["name"] == "SchemaX"
    assert b["prompt_cache_key"] == "pck-synth-1" and b["max_output_tokens"] == 800 and b["input"]
    for banned in ("tools", "tool_choice", "functions", "response_format", "messages", "max_tokens"):
        assert banned not in b


def test_S33_empty_input_rejected_before_network(tmp_path):
    rig = Rig(tmp_path)
    for bad in ("", "   "):
        r = rig.client.call(**call_args(0, input=bad)).record
        assert r.status == "error" and r.error["code"] == "invalid_request" and r.cost_usd_micros is None
    assert rig.tr.calls == 0


def test_S33_model_id_comes_from_config(tmp_path):
    m = model_cfg()
    m["profiles"]["meta"]["model"] = "muse-test-model"
    rig = Rig(tmp_path, model=m)
    rig.client.call(**call_args(0))
    assert rig.tr.requests[0]["body"]["model"] == "muse-test-model"


def test_S34_effort_from_config_per_role(tmp_path):
    m = model_cfg()
    m["effort"]["c"] = "minimal"
    rig = Rig(tmp_path, model=m)
    rc = rig.client.call(**call_args(0, role="c")).record
    ra = rig.client.call(**call_args(0, role="a")).record
    assert rig.tr.requests[0]["body"]["reasoning"]["effort"] == "minimal" and rc.effort == "minimal"
    assert rig.tr.requests[1]["body"]["reasoning"]["effort"] == "low" and ra.effort == "low"
    assert rc.cache_key != ra.cache_key  # hanya effort yang beda


def test_S34_effort_rejected_by_server_and_unknown_role(tmp_path):
    m = model_cfg()
    m["effort"]["c"] = "max"
    rig = Rig(tmp_path, model=m, script=[Resp(400, {"error": {"message": "reasoning.effort 'max' is not supported"}})])
    r = rig.client.call(**call_args(0)).record
    assert rig.tr.calls == 1 and r.status == "error" and r.error["code"] == "invalid_request"
    assert "'max'" in r.error["message"] and "not supported" in r.error["message"]
    assert r.effort == "max"
    assert not list((rig.runs / "spark" / "c").glob("*.json"))
    from backend.spark import ConfigInvalid
    with pytest.raises(ConfigInvalid):
        rig.client.call(**call_args(0, role="zzz"))
    assert rig.tr.calls == 1


def test_S35_openrouter_not_reportable(tmp_path):
    dev = Rig(tmp_path, profile="openrouter_dev")
    r_dev = dev.client.call(**call_args(0)).record
    r_meta = dev.new_client("meta").call(**call_args(1)).record
    assert (r_dev.provider, r_dev.model, r_dev.cost_usd_micros) == ("openrouter", "meta/muse-spark-1.3-contributor", 414)
    require_reportable([r_meta])
    before = r_dev.to_dict()
    for batch in ([r_dev], [r_meta, r_dev], [r_dev.to_dict()]):
        with pytest.raises(NotReportable) as ei:
            require_reportable(batch)
        assert "openrouter_dev" in str(ei.value) and "H-057" in str(ei.value)
    assert r_dev.to_dict() == before
    # profil meta yang dibalik for_reported_numbers=false di config juga ditolak
    m = model_cfg()
    m["profiles"]["meta"]["for_reported_numbers"] = False
    with pytest.raises(NotReportable):
        require_reportable([r_meta], m)
    require_reportable([r_meta], model_cfg())


# ---- S37: GET /api/runs ----

def _app(runs, extra=None):
    return TestClient(create_app(env=env_ok(), runs_dir=runs, model_config=model_cfg(), budget_config=budget_cfg()))


def _seed(runs, with_r4):
    def mk(rid, kind_role, t, status="ok"):
        synth(runs, kind_role, "meta", 5, run_id=rid)
        p = store.spark_dir(runs) / "records" / f"{rid}.json"
        rec = RunRecord.from_dict(__import__("json").loads(p.read_text(encoding="utf-8")))
        rec.created_at = f"2026-10-27T10:0{t}:00Z"
        rec.status = status
        store.save_record(runs, rec)
    mk("r1", "a", 0)
    mk("r2", "c", 1)
    mk("r3", "c", 2)
    if with_r4:
        mk("r4", "c", 3, "cached")


def _ids(resp):
    assert resp.status_code == 200
    return [r["run_id"] for r in resp.json()]


def test_S37_runs_listing_without_cache_hit_record(tmp_path):
    _seed(tmp_path / "runs", with_r4=False)
    c = _app(tmp_path / "runs")
    assert _ids(c.get("/api/runs", params={"kind": "spark_c", "limit": 1})) == ["r3"]
    assert _ids(c.get("/api/runs", params={"kind": "spark_c"})) == ["r3", "r2"]
    assert _ids(c.get("/api/runs")) == ["r3", "r2", "r1"]


def test_S37_runs_listing_with_cache_hit_record_and_errors(tmp_path):
    _seed(tmp_path / "runs", with_r4=True)
    c = _app(tmp_path / "runs")
    assert _ids(c.get("/api/runs", params={"kind": "spark_c", "limit": 1})) == ["r4"]
    assert _ids(c.get("/api/runs", params={"kind": "spark_c"})) == ["r4", "r3", "r2"]
    assert _ids(c.get("/api/runs")) == ["r4", "r3", "r2", "r1"]
    body = c.get("/api/runs").json()
    assert set(body[0]) == {f.name for f in fields(RunRecord)}
    assert scan_text(c.get("/api/runs").text, with_k2=True) == []
    bad = c.get("/api/runs", params={"kind": "bogus"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_request" and bad.json()["error"]["message"]
    zero = c.get("/api/runs", params={"limit": 0})  # dipilih: 400 invalid_request (bukan crash)
    assert zero.status_code == 400 and zero.json()["error"]["code"] == "invalid_request"
    assert c.get("/api/runs", params={"limit": "abc"}).status_code == 400


def test_S37_real_calls_appear_in_listing(tmp_path):
    rig = Rig(tmp_path)
    rig.client.call(**call_args(0))
    rig.client.call(**call_args(0))  # hit cache menulis record baru (O-7)
    rows = _app(rig.runs).get("/api/runs", params={"kind": "spark_c"}).json()
    assert sorted(r["status"] for r in rows) == ["cached", "ok"] and rig.tr.calls == 1


# ---- S38: pra-validasi skema strict ----

def _mini(**over):
    s = {
        "type": "object", "additionalProperties": False, "required": ["status", "jawaban", "kutipan"],
        "properties": {
            "status": {"type": "string"}, "jawaban": {"type": "string"},
            "kutipan": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["alamat", "teks", "catatan"],
                "properties": {"alamat": {"type": "string"}, "teks": {"type": "string"},
                               "catatan": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}},
        },
    }
    s.update(over)
    return s


def _variant(fn):
    s = copy.deepcopy(_mini())
    fn(s)
    return s


BAD = {
    "a_root_no_addl": _variant(lambda s: s.pop("additionalProperties")),
    "b_nested_no_addl": _variant(lambda s: s["properties"]["kutipan"]["items"].pop("additionalProperties")),
    "c_nested_required_incomplete": _variant(lambda s: s["properties"]["kutipan"]["items"].__setitem__("required", ["alamat", "catatan"])),
    "d_oneof_in_anyof_nested": _variant(lambda s: s["properties"].__setitem__("jawaban", {"anyOf": [{"oneOf": [{"type": "string"}, {"type": "null"}]}]})),
    "e_allof_root": _variant(lambda s: s.__setitem__("allOf", [{"type": "object"}])),
    "f_anyof_root": {"anyOf": [_mini(), _mini()]},
    "g_recursive_ref": {
        "type": "object", "additionalProperties": False, "required": ["node"],
        "properties": {"node": {"$ref": "#/$defs/node"}},
        "$defs": {"node": {"type": "object", "additionalProperties": False, "required": ["child"],
                           "properties": {"child": {"anyOf": [{"$ref": "#/$defs/node"}, {"type": "null"}]}}}},
    },
    "h_optional_not_required": _variant(lambda s: s["properties"]["kutipan"]["items"].__setitem__("required", ["alamat", "teks"])),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_S38_invalid_strict_schema_rejected_before_network(tmp_path, name):
    rig = Rig(tmp_path)
    res = rig.client.call(**call_args(0, schema=BAD[name], schema_name="AnswerCMini"))
    r = res.record
    assert r.status == "error" and r.error["code"] == "schema_invalid" and r.cost_usd_micros is None
    assert rig.tr.calls == 0 and res.output is None


def test_S38_valid_nested_schema_with_optional_via_anyof_is_sent(tmp_path):
    out = {"status": "tolak", "jawaban": "x", "kutipan": [{"alamat": "p1", "teks": "t", "catatan": None}]}
    rig = Rig(tmp_path, default=Resp(200, body_ok(output=out)))
    res = rig.client.call(**call_args(0, schema=_mini(), schema_name="AnswerCMini"))
    assert res.record.status == "ok" and rig.tr.calls == 1
    assert rig.tr.requests[0]["body"]["text"]["format"]["schema"] == _mini()


def test_S38_bad_schema_name_rejected(tmp_path):
    rig = Rig(tmp_path)
    r = rig.client.call(**call_args(0, schema_name="")).record
    assert r.error["code"] == "schema_invalid" and rig.tr.calls == 0


def test_failed_settings_optional_field_roundtrip():
    from backend.spark.runrecord import RunRecord

    base = dict(run_id="r", kind="grid", created_at="2026-10-27T00:00:00Z", cache_key="k", corpus_hash=None, config_hash=None,
                clean_sha256=None, loader_rules_version=None, prompt_version=None, prompt_hash=None, model=None, effort=None,
                tokenizer=None, embedder=None, packing=None, usage_input_tokens=None, usage_cached_tokens=None,
                usage_output_tokens=None, cost_usd_micros=0, projected_cost_usd_micros=5, latency_ms=1, host="h", device="cpu",
                provider=None, quantization=None, status="ok", error=None)
    old = RunRecord(**base)
    legacy = {k: v for k, v in old.to_dict().items() if k != "failed_settings"}
    assert old.to_dict()["failed_settings"] is None and RunRecord.from_dict(legacy) == old  # record lama terbaca
    assert RunRecord.from_dict(old.to_dict()) == old
    fs = [{"setting_id": "s+", "reason": "header_missing", "chunk_id": "c4"}]
    new = RunRecord(**base, failed_settings=fs)
    assert RunRecord.from_dict(new.to_dict()) == new and new.to_dict()["failed_settings"] == fs
    assert new.spend_micros() == old.spend_micros() == 5
    with pytest.raises(ValueError):
        RunRecord.from_dict({**old.to_dict(), "failed_settings": "x"})
