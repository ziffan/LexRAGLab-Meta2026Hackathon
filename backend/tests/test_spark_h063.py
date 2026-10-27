"""M0.1 amandemen H-063 (A1-A9): panggilan gagal tanpa usage (timeout habis, 5xx, galat koneksi) mengisi
`projected_cost_usd_micros`; buku belanja dan guard memakai `cost ?? projected`. Skenario: _kerja/orkestrasi/l3/W1-H063-hasil.md."""

import json

import httpx2
import pytest

from backend.spark import BudgetExceeded, Ledger
from backend.tests.spark_fakes import Resp, Rig, Timeout, body_ok, budget_cfg, call_args

EST = dict(est_input=3000, max_output_tokens=500)  # 3000*0.1 + 500*0.2 = 400 micro-USD (S26)


def _a(n=0, **over):
    return call_args(n, **EST, **over)


def _raise_connect(tr, request):
    raise httpx2.ConnectError("connection refused")


def _assert_projected(res, code):
    r = res.record
    assert r.status == "error" and r.error["code"] == code
    assert r.cost_usd_micros is None and r.projected_cost_usd_micros == 400
    assert r.usage_input_tokens is None and res.output is None
    assert type(r.projected_cost_usd_micros) is int
    assert "\n" not in r.error["message"]


def _records(rig):
    return list((rig.runs / "spark" / "records").glob("*.json"))


def test_A1_timeout_exhausted_projects_400(tmp_path):
    rig = Rig(tmp_path, script=[Timeout(), Timeout()])
    res = rig.client.call(**_a())
    assert rig.tr.calls == 2
    _assert_projected(res, "timeout")
    assert len(_records(rig)) == 1  # satu record per panggilan logis
    assert Ledger(rig.runs).spent() == 400


@pytest.mark.parametrize("status,code", [(500, "model_error"), (502, "model_unavailable"),
                                         (503, "model_unavailable"), (504, "model_unavailable")])
def test_A2_5xx_projects_400(tmp_path, status, code):
    rig = Rig(tmp_path, script=[Resp(status, {"error": {"message": "boom"}})])
    res = rig.client.call(**_a())
    assert rig.tr.calls == 1
    _assert_projected(res, code)
    assert Ledger(rig.runs).spent() == 400


def test_A3_connection_error_projects_400(tmp_path):
    rig = Rig(tmp_path, script=[_raise_connect])
    res = rig.client.call(**_a())
    _assert_projected(res, "model_unavailable")
    assert res.record.error["message"] == "connection to the Model API failed"
    assert Ledger(rig.runs).spent() == 400


@pytest.mark.parametrize("label,script,code", [
    ("401", [Resp(401, {"error": {"message": "bad"}})], "invalid_api_key"),
    ("400", [Resp(400, {"error": {"message": "bad"}})], "invalid_request"),
    ("404", [Resp(404, {"error": {"message": "nope"}})], "model_unavailable"),
    ("422", [Resp(422, text="<html>x</html>")], "invalid_request"),
])
def test_A4_rejected_before_generation_stays_null(tmp_path, label, script, code):
    rig = Rig(tmp_path, script=script)
    r = rig.client.call(**_a()).record
    assert r.error["code"] == code and r.cost_usd_micros is None and r.projected_cost_usd_micros is None
    assert Ledger(rig.runs).spent() == 0


def test_A4b_timeout_then_401_stays_null(tmp_path):
    rig = Rig(tmp_path, script=[Timeout(), Resp(401, {"error": {"message": "bad"}})])
    r = rig.client.call(**_a()).record
    assert r.error["code"] == "invalid_api_key" and r.projected_cost_usd_micros is None


def test_A5_429_exhausted_stays_null(tmp_path):
    rig = Rig(tmp_path, script=[Resp(429, {"error": {"message": "slow"}})] * 4)
    r = rig.client.call(**_a()).record
    assert rig.tr.calls == 4 and r.error["code"] == "rate_limited"
    assert r.cost_usd_micros is None and r.projected_cost_usd_micros is None
    assert Ledger(rig.runs).spent() == 0


def test_A6_timeout_then_success_bills_usage_only(tmp_path):
    rig = Rig(tmp_path, script=[Timeout(), Resp(200, body_ok(usage={"input_tokens": 3000, "output_tokens": 500}))])
    r = rig.client.call(**_a()).record
    assert r.status == "ok" and r.cost_usd_micros == 400 and r.projected_cost_usd_micros is None
    assert len(_records(rig)) == 1 and Ledger(rig.runs).spent() == 400


def test_A7_ledger_from_disk_sums_and_new_client_sees_it(tmp_path):
    rig = Rig(tmp_path, script=[Timeout(), Timeout(), Resp(503, {"error": {"message": "x"}}), _raise_connect,
                           Resp(500, {"error": {"message": "x"}})])
    for i in range(4):
        rig.client.call(**_a(i))
    assert Ledger(rig.runs).spent() == 1600 and Ledger(rig.runs).spent(role="c") == 1600
    fresh = rig.new_client()
    assert fresh.project_batch([_a(9)]).spent_micros == 1600
    on_disk = [json.loads(p.read_text(encoding="utf-8")) for p in _records(rig)]
    assert sorted(d["projected_cost_usd_micros"] for d in on_disk) == [400] * 4
    assert all(d["cost_usd_micros"] is None for d in on_disk)


def test_A8_guard_rejects_next_call_after_two_timeouts(tmp_path):
    rig = Rig(tmp_path, budget=budget_cfg(total=10_000_000, role=1000), script=[Timeout()] * 4)
    rig.client.call(**_a(0))
    rig.client.call(**_a(1))
    assert rig.tr.calls == 4 and Ledger(rig.runs).spent() == 800
    with pytest.raises(BudgetExceeded) as ei:
        rig.client.call(**_a(2))  # 800 + 400 = 1200 > 1000
    assert "1200" in str(ei.value) and rig.tr.calls == 4
    # klien baru (dibaca ulang dari disk) menolak juga; batas inklusif: 800 + 200 lolos proyeksi
    assert rig.new_client().project_batch([_a(2)]).verdict == "budget_exceeded"
    assert rig.new_client().project_batch([call_args(2, est_input=1000, max_output_tokens=500)]).verdict == "ok"


def test_A8b_mid_batch_stops_when_failed_calls_exhaust_cap(tmp_path):
    # role cap 1200: proyeksi awal 3 x 400 = 1200 lolos; panggilan 1-3 timeout -> belanja 400, 800, 1200
    rig = Rig(tmp_path, budget=budget_cfg(total=10_000_000, role=1200), script=[Timeout()] * 6)
    out = rig.client.run_batch([_a(i) for i in range(3)])
    assert out.stopped_reason is None and rig.tr.calls == 6 and Ledger(rig.runs).spent() == 1200
    with pytest.raises(BudgetExceeded):
        rig.client.run_batch([_a(7)])  # 1200 + 400 > 1200 ditolak sebelum jaringan
    assert rig.tr.calls == 6


def test_A9_cache_hit_unaffected(tmp_path):
    rig = Rig(tmp_path, default=Resp(200, body_ok(usage={"input_tokens": 3000, "output_tokens": 500})))
    assert rig.client.call(**_a(0)).record.cost_usd_micros == 400
    hit = rig.client.call(**_a(0)).record
    assert hit.status == "cached" and hit.cost_usd_micros == 0 and hit.projected_cost_usd_micros is None
    assert rig.tr.calls == 1 and Ledger(rig.runs).spent() == 400
