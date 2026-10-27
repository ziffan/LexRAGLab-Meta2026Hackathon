"""M0.1 S13-S19, S41, S42: pembatas laju jendela geser, Retry-After, backoff, retry timeout, berurutan."""

from datetime import UTC, datetime

import pytest

from backend.spark import ConfigInvalid, load_configs
from backend.tests.spark_fakes import (
    Clock,
    Resp,
    Rig,
    Timeout,
    body_ok,
    call_args,
    model_cfg,
)


def _cfg(**limits):
    m = model_cfg()
    m["limits"].update(limits)
    return m


def _max_in_window(starts, width=60.0):
    return max(sum(1 for t in starts if s <= t < s + width) for s in starts)


def test_S13_sliding_window_limiter(tmp_path):
    rig = Rig(tmp_path, model=_cfg(max_rpm=4), clock=Clock(59.0))
    for i in range(9):
        assert rig.client.call(**call_args(i)).record.status == "ok"
    s = rig.tr.starts
    assert len(s) == 9
    assert _max_in_window(s) <= 4
    assert s[4] - s[0] >= 60 and s[8] - s[0] >= 120
    assert s[:4] == [59.0] * 4 and s[4] >= 119.0 and s[8] >= 179.0


@pytest.mark.parametrize("fail", [Resp(429, {"error": {"message": "slow"}}, headers={"Retry-After": "1"}), Timeout()])
def test_S14_retries_count_toward_rpm(tmp_path, fail):
    rig = Rig(tmp_path, model=_cfg(max_rpm=4), script=["ok", "ok", "ok", fail, "ok"], clock=Clock(1000.0))
    for i in range(4):
        assert rig.client.call(**call_args(i)).record.status == "ok"
    s = rig.tr.starts
    assert len(s) == 5
    assert s[:4] == [1000.0] * 4
    assert s[4] >= 1060.0  # jendela [1000,1060) sudah berisi 4, walau Retry-After hanya 1 s
    assert _max_in_window(s) <= 4


def test_S14_real_config_and_limits_validated(tmp_path):
    model, _ = load_configs()
    assert model["limits"]["max_rpm"] == 140
    for bad in (150, 3000, 0):
        with pytest.raises(ConfigInvalid):
            Rig(tmp_path, model=_cfg(max_rpm=bad))
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("header", ["Retry-After", "retry-after"])
def test_S15_retry_after_honored(tmp_path, header):
    rig = Rig(tmp_path, script=[Resp(429, {"error": {"message": "slow"}}, headers={header: "7"}),
                                Resp(200, body_ok(), advance=2.5)])
    res = rig.client.call(**call_args(0))
    s = rig.tr.starts
    assert rig.tr.calls == 2 and 1007.0 <= s[1] < 1008.0
    assert res.record.status == "ok" and res.record.cost_usd_micros == 414
    assert len(list((rig.runs / "spark" / "records").glob("*.json"))) == 1  # satu record
    assert res.record.latency_ms == 9500 and type(res.record.latency_ms) is int  # O-8


def _r429(**headers):
    return Resp(429, {"error": {"message": "slow"}}, headers=headers)


def test_S16a_429_exhausts_after_three_retries(tmp_path):
    rig = Rig(tmp_path, script=[_r429()] * 4, clock=Clock(0.0))
    res = rig.client.call(**call_args(0))
    assert rig.tr.starts == [0.0, 2.0, 6.0, 14.0]
    assert res.record.status == "error" and res.record.error["code"] == "rate_limited"
    assert res.record.cost_usd_micros is None
    assert not list((rig.runs / "spark" / "c").glob("*.json"))


def test_S16b_backoff_then_success(tmp_path):
    rig = Rig(tmp_path, script=[_r429(), _r429(), "ok"], clock=Clock(0.0))
    res = rig.client.call(**call_args(0))
    assert res.record.status == "ok" and rig.tr.starts == [0.0, 2.0, 6.0]


@pytest.mark.parametrize("value", ["abc", "-5", "", "  "])
def test_S16cd_invalid_retry_after_uses_backoff(tmp_path, value):
    rig = Rig(tmp_path, script=[_r429(**{"Retry-After": value}), "ok"], clock=Clock(0.0))
    res = rig.client.call(**call_args(0))
    assert res.record.status == "ok" and rig.clock.sleeps == [2]


def test_S16e_http_date_retry_after(tmp_path):
    t0 = datetime(2026, 10, 27, 10, 0, 0, tzinfo=UTC).timestamp()
    rig = Rig(tmp_path, script=[_r429(**{"Retry-After": "Tue, 27 Oct 2026 10:00:07 GMT"}), "ok"], clock=Clock(t0))
    assert rig.client.call(**call_args(0)).record.status == "ok"
    assert rig.clock.sleeps == [7.0]


def test_S16f_small_and_zero_retry_after(tmp_path):
    rig = Rig(tmp_path, script=[_r429(**{"Retry-After": "1"}), "ok"], clock=Clock(0.0))
    rig.client.call(**call_args(0))
    assert rig.clock.sleeps == [1.0]  # otoritatif walau < backoff 2
    rig2 = Rig(tmp_path / "z", script=[_r429(**{"Retry-After": "0"}), "ok"], clock=Clock(0.0))
    assert rig2.client.call(**call_args(0)).record.status == "ok"
    assert rig2.clock.sleeps == [] and rig2.tr.calls == 2


def test_S16f_zero_retry_after_still_subject_to_limiter(tmp_path):
    rig = Rig(tmp_path, model=_cfg(max_rpm=1), script=[_r429(**{"Retry-After": "0"}), "ok"], clock=Clock(0.0))
    rig.client.call(**call_args(0))
    assert rig.tr.starts[1] >= 60.0


@pytest.mark.parametrize("label,script,ok,sleeps,code", [
    ("a_3600", [_r429(**{"Retry-After": "3600"})], False, [], "rate_limited"),
    ("b_120_inclusive", [_r429(**{"Retry-After": "120"}), "ok"], True, [120.0], None),
    ("c_121", [_r429(**{"Retry-After": "121"})], False, [], "rate_limited"),
    ("d_119_5", [_r429(**{"Retry-After": "119.5"}), "ok"], True, [119.5], None),
])
def test_S17_retry_after_max_wait(tmp_path, label, script, ok, sleeps, code):
    rig = Rig(tmp_path, script=script, clock=Clock(0.0))
    res = rig.client.call(**call_args(0))
    assert rig.clock.sleeps == sleeps and all(x <= 120 for x in rig.clock.sleeps)
    assert rig.tr.calls == len(script)
    if ok:
        assert res.record.status == "ok"
    else:
        assert res.record.status == "error" and res.record.error["code"] == code
        assert label[2:].split("_")[0] in res.record.error["message"] and "max_wait_s" in res.record.error["message"]


@pytest.mark.parametrize("label,script,max_retries,calls,status,code", [
    ("a", [Timeout(), "ok"], 1, 2, "ok", None),
    ("b", [Timeout(), Timeout()], 1, 2, "error", "timeout"),
    ("c", [Timeout(), Timeout()], 0, 1, "error", "timeout"),
    ("d", [Timeout(), Timeout(), Timeout()], 2, 3, "error", "timeout"),
    ("e", [Timeout(), Resp(401, {"error": {"message": "bad"}})], 1, 2, "error", "invalid_api_key"),
])
def test_S18_timeout_retries_from_config(tmp_path, label, script, max_retries, calls, status, code):
    rig = Rig(tmp_path, model=_cfg(max_retries=max_retries), script=script)
    res = rig.client.call(**call_args(0))
    assert rig.tr.calls == calls
    assert all(q["timeout"]["read"] == 120 for q in rig.tr.requests)
    assert res.record.status == status
    if code:
        assert res.record.error["code"] == code
    else:
        assert res.record.cost_usd_micros == 414


def test_S19_sequential_in_input_order(tmp_path):
    rig = Rig(tmp_path)
    calls = [call_args(i) for i in range(5)]
    out = rig.client.run_batch(calls)
    assert rig.tr.max_active == 1
    assert [q["input"] for q in rig.tr.requests] == [c["input"] for c in calls]
    assert [r.record.status for r in out.results] == ["ok"] * 5 and out.not_run == [] and out.stopped_reason is None
    assert [r.record.cache_key for r in out.results] == [rig.client._key_for(c, "low") for c in calls]


def test_S41_limiter_shared_between_client_instances(tmp_path):
    rig = Rig(tmp_path, model=_cfg(max_rpm=4), clock=Clock(1000.0))
    a, b = rig.client, rig.new_client()
    for i in range(9):
        (a if i % 2 == 0 else b).call(**call_args(i))
    s = rig.tr.starts
    assert _max_in_window(s) <= 4 and s[4] - s[0] >= 60 and s[8] - s[0] >= 120
    assert s[4] >= 1060.0 and s[8] >= 1120.0


def test_S41_variant_other_provider_not_blocked(tmp_path):
    rig = Rig(tmp_path, model=_cfg(max_rpm=4), clock=Clock(1000.0))
    dev = rig.new_client("openrouter_dev")
    for i in range(4):
        rig.client.call(**call_args(i))
    for i in range(10, 14):
        dev.call(**call_args(i))
    assert rig.tr.starts == [1000.0] * 8 and rig.clock.sleeps == []


@pytest.mark.parametrize("label,script,calls,status,code", [
    ("a", [Timeout(), _r429(), _r429(), _r429(), "ok"], 5, "ok", None),
    ("b", [_r429(), Timeout(), Timeout()], 3, "error", "timeout"),
    ("c", [_r429(), _r429(), _r429(), Timeout(), Timeout()], 5, "error", "timeout"),
    ("d", [Timeout(), _r429(), Timeout()], 3, "error", "timeout"),
])
def test_S42_separate_counters_for_timeout_and_429(tmp_path, label, script, calls, status, code):
    rig = Rig(tmp_path, script=script, clock=Clock(0.0))
    res = rig.client.call(**call_args(0))
    assert rig.tr.calls == calls and res.record.status == status
    if code:
        assert res.record.error["code"] == code
