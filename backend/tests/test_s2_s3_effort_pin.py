"""M3.2-effort-sweep S2 (pin effort benar-benar DIKIRIM) dan S3 (pemeriksaan pantulan effort, P5). Transport palsu."""

import pytest

from backend.spark import store
from .m25_fakes import chat_body
from .spark_fakes import OUT_OK, Resp, body_ok, call_args
from .sweep_helpers import USAGE_40K, make_client

SHA_X = "e1385ec978e3acd13c13b5de14fdc6d385e91f60eaf718e2a211e68ea7b89263"


def args(**kw):
    return call_args(0, role="b", prompt_hash="P1", schema_hash="S1", input="input-x", **kw)


def test_s2_a_meta_sweep_sends_pin_and_records_it(tmp_path):
    c, tr = make_client(tmp_path, "sweep_meta_medium", default=Resp(200, body_ok(reasoning={"effort": "medium"})))
    assert c._effort("b") == "medium"
    res = c.call(**args())
    assert tr.requests[0]["body"]["reasoning"] == {"effort": "medium"}
    r = res.record
    assert (r.effort, r.provider, r.model, r.status) == ("medium", "meta", "muse-spark-1.3-contributor", "ok")
    assert r.cache_key == "87b0cce8cc6141e076bac67cee40e1efeddcd4d3d388e49be26854892aacb45e"
    assert tr.requests[0]["body"]["max_output_tokens"] == max(800, 6000)  # floor sapuan 6.000 (P6)


def test_s2_a_baseten_and_glimmer_sweep(tmp_path):
    c, tr = make_client(tmp_path, "sweep_baseten_high", default=Resp(200, body_ok(reasoning={"effort": "high"})))
    res = c.call(**args())
    assert tr.requests[0]["body"]["reasoning"] == {"effort": "high"}
    assert (res.record.effort, res.record.provider) == ("high", "baseten")
    g, trg = make_client(tmp_path / "g", "sweep_glimmer_xhigh", default=Resp(200, chat_body(OUT_OK)))
    res = g.call(**args())
    assert trg.requests[0]["body"]["reasoning_effort"] == "xhigh" and trg.requests[0]["path"].endswith("/chat/completions")
    assert res.record.effort == "xhigh" and res.record.provider == "lmstudio_local" and res.record.status == "ok"


def test_s2_b_sweep_never_cache_hits_main(tmp_path):
    main, trm = make_client(tmp_path, "meta")
    sw, trs = make_client(tmp_path, "sweep_meta_medium", default=Resp(200, body_ok(reasoning={"effort": "medium"})))
    assert main.call(**args()).record.cache_key == "0ccf23a7e2fb969ae86923cf8199c721cbfb0e719d1947a61b7683307ffe5fea"
    r = sw.call(**args())
    assert r.record.status == "ok" and trs.calls == 1  # tidak cache-hit dari data utama `low`
    again = main.call(**args())
    assert again.record.status == "cached" and trm.calls == 1  # dan sebaliknya


def test_s2_c_existing_profiles_have_no_pin(tmp_path):
    for prof in ("meta", "openrouter_dev", "baseten_open"):
        c, _ = make_client(tmp_path / prof, prof)
        assert c._s.effort_override is None and c._effort("b") == "low"
    g, _ = make_client(tmp_path / "g", "glimmer_local")
    assert g._s.effort_override == "high"


# ------------------------------------------------------------------ S3
def _bt(tmp_path, reasoning, **kw):
    body = body_ok(usage=USAGE_40K, **({"reasoning": reasoning} if reasoning is not None else {}))
    return make_client(tmp_path, "sweep_baseten_medium", default=Resp(200, body), **kw)


def test_s3_a_reflected_equal_is_success(tmp_path):
    c, tr = _bt(tmp_path, {"effort": "medium"})
    res = c.call(**args())
    assert res.record.status == "ok" and res.output is not None


def test_s3_b_mismatch_fails_closed_keeps_cost_and_no_cache(tmp_path):
    c, tr = _bt(tmp_path, {"effort": "xhigh"})
    res = c.call(**args())
    r = res.record
    assert r.status == "error" and r.error["code"] == "effort_mismatch" and res.output is None
    assert "medium" in r.error["message"] and "xhigh" in r.error["message"]
    assert r.cost_usd_micros == 9_350  # (300 x 1.250.000 + 40.000 x 150.000 + 700 x 4.250.000) / 1e6
    assert store.cache_read(c._runs, "b", r.cache_key) is None
    assert not (c._runs / "rejected").exists()
    c.call(**args())
    assert tr.calls == 2  # panggilan berikutnya tidak cache-hit: ke jaringan lagi


def test_s3_c_missing_reasoning_field_fails_closed(tmp_path):
    c, _ = _bt(tmp_path, None)
    res = c.call(**args())
    assert res.record.status == "error" and res.record.error["code"] == "effort_mismatch"
    assert res.record.cost_usd_micros == 9_350


def test_s3_d_unpinned_profiles_not_checked(tmp_path):
    for prof in ("baseten_open", "meta"):
        for reasoning in ({"effort": "xhigh"}, None):
            c, _ = make_client(tmp_path / f"{prof}-{'x' if reasoning else 'none'}", prof,
                               default=Resp(200, body_ok(**({"reasoning": reasoning} if reasoning else {}))))
            assert c.call(**args()).record.status == "ok", (prof, reasoning)


def test_s3_e_glimmer_sweep_not_checked(tmp_path):
    g, _ = make_client(tmp_path, "sweep_glimmer_medium", default=Resp(200, chat_body(OUT_OK)))
    res = g.call(**args())
    assert res.record.status == "ok" and res.record.effort == "medium"


def test_s3_message_has_no_key_or_url(tmp_path):
    from .spark_fakes import scan_result
    c, _ = _bt(tmp_path, {"effort": "xhigh"})
    assert scan_result(c.call(**args())) == []
