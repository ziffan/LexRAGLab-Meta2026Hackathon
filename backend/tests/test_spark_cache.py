"""M0.1 S20-S25, S36: cache per hash, sensitivitas kunci, kanonisasi, galat tidak di-cache, replay."""

import hashlib
import json

import pytest

from backend.spark import Ledger
from backend.tests.spark_fakes import (
    K2,
    Clock,
    K,
    Resp,
    Rig,
    body_ok,
    call_args,
    env_ok,
    model_cfg,
)


def _files(runs):
    return sorted(str(p.relative_to(runs)) for p in runs.rglob("*") if p.is_file()) if runs.exists() else []


def test_S20_cache_hit_no_network_and_records(tmp_path):
    rig = Rig(tmp_path)
    a = call_args(0)
    r1 = rig.client.call(**a)
    r2 = rig.client.call(**a)
    assert rig.tr.calls == 1
    assert r2.record.status == "cached" and r2.record.cache_key == r1.record.cache_key
    assert r2.output == r1.output
    assert r2.record.cost_usd_micros == 0 and r2.record.run_id != r1.record.run_id
    assert (r2.record.usage_input_tokens, r2.record.usage_cached_tokens, r2.record.usage_output_tokens) == (None, None, None)
    # klien BARU dengan runs/ yang sama
    r3 = rig.new_client().call(**a)
    assert rig.tr.calls == 1 and r3.record.status == "cached" and r3.output == r1.output
    assert Ledger(rig.runs).spent() == 414  # hit tidak menambah belanja
    # berkas cache dipotong separuh -> miss, ditulis ulang valid
    path = next((rig.runs / "spark" / "c").glob("*.json"))
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) // 2])
    r4 = rig.client.call(**a)
    assert rig.tr.calls == 2 and r4.record.status == "ok"
    assert json.loads(path.read_text(encoding="utf-8"))["output"] == r1.output
    assert rig.client.call(**a).record.status == "cached" and rig.tr.calls == 2


def test_S20_cache_hits_do_not_consume_rpm(tmp_path):
    m = model_cfg()
    m["limits"]["max_rpm"] = 4
    rig = Rig(tmp_path, model=m, clock=Clock(1000.0))
    for i in range(4):
        rig.client.call(**call_args(i))
    for _ in range(10):
        assert rig.client.call(**call_args(0)).record.status == "cached"
    assert rig.clock.sleeps == [] and rig.tr.calls == 4
    assert len(list((rig.runs / "spark" / "records").glob("*.json"))) == 14  # tiap hit menulis record


def test_S21_cache_key_sensitivity_seven_components(tmp_path):
    base = Rig(tmp_path)
    keys, calls = [], []

    def run(client, **over):
        kw = dict(prompt_hash="P", schema_hash="S", input="I")
        kw.update(over)
        res = client.call(**call_args(0, **kw))
        keys.append(res.record.cache_key)
        calls.append(base.tr.calls)
        assert res.record.status == "ok"

    run(base.client)  # B
    run(base.new_client("meta2"))  # provider
    m_model = model_cfg(); m_model["profiles"]["meta"]["model"] = "muse-spark-1.3"
    m_quant = model_cfg(); m_quant["profiles"]["meta"]["quantization"] = "Q4_K_M"
    m_eff = model_cfg(); m_eff["effort"]["c"] = "minimal"
    for m in (m_model, m_quant, m_eff):
        base.model = m
        run(base.new_client())
    base.model = model_cfg()
    run(base.client, prompt_hash="P2")
    run(base.client, schema_hash="S2")
    run(base.client, input="I2")
    assert len(set(keys)) == 8 and calls == list(range(1, 9))
    # invarian: key API dan prompt_cache_key berbeda -> HIT
    other = base.new_client(env=env_ok(**{"MUSE_API_KEY": K2}))
    hit = other.call(**call_args(0, prompt_hash="P", schema_hash="S", input="I", prompt_cache_key="pck-other"))
    assert hit.record.status == "cached" and base.tr.calls == 8 and hit.record.cache_key == keys[0]
    assert all(K not in k and K2 not in k for k in keys)


def test_S22_output_canonicalized(tmp_path):
    rig = Rig(tmp_path, script=[
        Resp(200, body_ok(text='{"jawaban":"x","kutipan":[],"status":"tolak"}')),
        Resp(200, body_ok(text='{ "status": "tolak", "kutipan": [], "jawaban": "x" }')),
    ])
    a = rig.client.call(**call_args(1))
    b = rig.client.call(**call_args(2))
    assert a.parsed == b.parsed and a.output == b.output
    assert hashlib.sha256(a.output.encode()).hexdigest() == hashlib.sha256(b.output.encode()).hexdigest()
    assert a.output == '{"jawaban":"x","kutipan":[],"status":"tolak"}'
    stored = json.loads(next((rig.runs / "spark" / "c").glob("*.json")).read_text(encoding="utf-8"))
    assert stored["output"] == a.output


def test_S23_semantic_failure_not_cached_as_valid(tmp_path):
    accept = {"v": False}

    def validator(out):
        if out["status"] == "jawab" and not out["kutipan"]:
            return None if accept["v"] else "status jawab requires kutipan"
        return None

    reply = body_ok(output={"jawaban": "x", "kutipan": [], "status": "jawab"})
    rig = Rig(tmp_path, default=Resp(200, reply))
    a = call_args(0, validator=validator)
    r1 = rig.client.call(**a)
    assert r1.record.status == "error" and r1.record.error["code"] == "semantic_invalid"
    assert r1.record.cost_usd_micros == 414 and r1.record.usage_input_tokens == 3247 and r1.output is None
    assert not list((rig.runs / "spark" / "c").glob("*.json"))
    accept["v"] = True
    r2 = rig.client.call(**a)
    assert rig.tr.calls == 2 and r2.record.status == "ok" and r2.record.cost_usd_micros == 414
    r3 = rig.client.call(**a)
    assert rig.tr.calls == 2 and r3.record.status == "cached"
    assert Ledger(rig.runs).spent() == 828
    # validator tidak dilewati pada HIT: validator yang menolak -> bukan hasil sah
    accept["v"] = False
    r4 = rig.client.call(**a)
    assert rig.tr.calls == 3 and r4.record.status == "error"


@pytest.mark.parametrize("label,kw,code", [
    ("a_not_json", {"text": "maaf"}, "schema_invalid"),
    ("b_missing_status", {"output": {"jawaban": "x", "kutipan": []}}, "schema_invalid"),
    ("c_incomplete", {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                      "text": '{"jawaban":"x","kut'}, "incomplete"),
])
def test_S24_schema_or_truncated_not_cached_but_billed(tmp_path, label, kw, code):
    usage = {"input_tokens": 1000, "output_tokens": 100}
    rig = Rig(tmp_path, default=Resp(200, body_ok(usage=usage, **kw)))
    a = call_args(0)
    r = rig.client.call(**a)
    assert r.record.status == "error" and r.record.error["code"] == code and r.output is None
    assert r.record.cost_usd_micros == 120
    assert not list((rig.runs / "spark" / "c").glob("*.json"))
    assert rig.client.call(**a).record.status == "error" and rig.tr.calls == 2  # MISS lagi
    assert "Traceback" not in r.record.error["message"]


def test_S25_replay_hit_and_miss_read_only(tmp_path):
    src = Rig(tmp_path)
    a = call_args(0)
    first = src.client.call(**a)
    before = _files(src.runs)
    clock = Clock(5000.0)
    rep = Rig(tmp_path, replay=True, env={}, clock=clock)
    hit = rep.client.call(**a)
    assert hit.record.status == "replay" and hit.output == first.output
    assert rep.tr.calls == 0 and clock.t == 5000.0
    miss = rep.client.call(**call_args(1))
    assert miss.record.status == "error" and miss.record.error["code"] == "replay_no_stored_run"
    assert rep.tr.calls == 0 and _files(src.runs) == before  # tidak ada berkas baru


def test_S36_cache_isolated_between_providers(tmp_path):
    dev = Rig(tmp_path, profile="openrouter_dev")
    meta = dev.new_client("meta")
    a = call_args(0)
    r_dev = dev.client.call(**a)
    r_meta = meta.call(**a)
    assert dev.tr.calls == 2 and r_meta.record.status == "ok"
    assert r_dev.record.cache_key != r_meta.record.cache_key
    assert (r_dev.record.provider, r_meta.record.provider) == ("openrouter", "meta")
    # replay untuk permintaan meta tanpa hasil meta -> replay_no_stored_run walau ada hasil OpenRouter
    only_dev = Rig(tmp_path / "only", profile="openrouter_dev")
    only_dev.client.call(**a)
    rep = Rig(tmp_path / "only", profile="meta", replay=True, env={})
    miss = rep.client.call(**a)
    assert miss.record.error["code"] == "replay_no_stored_run" and rep.tr.calls == 0
