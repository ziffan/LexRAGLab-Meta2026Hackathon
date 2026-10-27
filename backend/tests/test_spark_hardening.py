"""Putaran 2 review Tier 1: logger SDK, pantulan host/key di pesan server, ceil besar, tepi limiter, Retry-After tanpa zona."""

import logging
from datetime import datetime, timezone

import pytest

from backend.spark import parse_retry_after
from backend.spark.ratelimit import SlidingWindowLimiter
from backend.spark import compute_cost_micros
from backend.tests.spark_fakes import HOST, K, Resp, Rig, call_args, scan_text

SDK = ("openai", "httpx", "httpx2", "httpcore", "httpcore2")


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@pytest.fixture
def fresh_sdk_loggers():
    saved = {}
    for name in list(logging.root.manager.loggerDict) + list(SDK):
        if name.split(".")[0] in SDK:
            lg = logging.getLogger(name)
            saved[name] = (lg.disabled, lg.propagate, lg.level)
            lg.disabled, lg.propagate = False, True
            lg.setLevel(logging.DEBUG)
    root = logging.getLogger()
    cap = _Capture()
    old_level = root.level
    root.addHandler(cap)
    root.setLevel(logging.DEBUG)
    yield cap
    root.removeHandler(cap)
    root.setLevel(old_level)
    for name, (d, p, lv) in saved.items():
        lg = logging.getLogger(name)
        lg.disabled, lg.propagate = d, p
        lg.setLevel(lv)


def test_S10_constructor_silences_fresh_sdk_loggers(tmp_path, fresh_sdk_loggers):
    cap = fresh_sdk_loggers
    logging.getLogger("httpx2").debug("control %s", HOST)
    assert any(HOST in ln for ln in cap.lines)  # kontrol: penangkap bekerja sebelum klien dibuat
    cap.lines.clear()
    rig = Rig(tmp_path)
    assert rig.client.call(**call_args(0)).record.status == "ok"
    late = logging.getLogger("httpx2.dibuat_belakangan")  # logger anak baru setelah konstruktor
    late.setLevel(logging.DEBUG)
    late.info("HTTP Request: POST https://%s/v1/responses key=%s", HOST, K)
    text = "\n".join(cap.lines)
    assert scan_text(text) == [] and "HTTP Request" not in text


@pytest.mark.parametrize("status,code", [(400, "invalid_request"), (404, "model_unavailable"),
                                         (500, "model_error"), (503, "model_unavailable")])
@pytest.mark.parametrize("variant", ["host_and_key", "host_only", "key_only"])
def test_S09_server_message_reflecting_host_and_key_is_redacted(tmp_path, status, code, variant):
    msgs = {"host_and_key": f"upstream https://{HOST}/v1 refused key {K}",
            "host_only": f"upstream {HOST} unreachable",
            "key_only": f"bad key {K}"}
    body = {"error": {"message": msgs[variant], "metadata": {"ineligibility_reasons": [msgs[variant]]}}}
    rig = Rig(tmp_path, script=[Resp(status, body)])
    r = rig.client.call(**call_args(0)).record
    assert r.error["code"] == code and rig.tr.calls == 1
    assert HOST not in r.error["message"] and K not in r.error["message"] and K[:8] not in r.error["message"]
    assert "[REDACTED]" in r.error["message"]
    assert scan_text(r.to_json()) == []


def test_S03_ceil_integer_above_2_pow_53():
    i = 2**53 + 1  # 9007199254740993; x100000 / 1e6 = 900719925474099.3
    got = compute_cost_micros({"input": i, "cached": 0, "output": 0},
                              {"input": 100000, "cached": 2000, "output": 200000})
    assert got == 900719925474100 and type(got) is int


def test_S13_limiter_exact_edge_does_not_hang():
    state = {"t": 1000.0, "sleeps": []}

    def sleep(s):
        state["sleeps"].append(s)
        assert len(state["sleeps"]) <= 3, "limiter loops without progress"
        state["t"] += s

    lim = SlidingWindowLimiter()
    now = lambda: state["t"]  # noqa: E731
    assert lim.acquire(2, now, sleep) == 1000.0 and lim.acquire(2, now, sleep) == 1000.0
    assert lim.acquire(2, now, sleep) == 1060.0  # tepat di tepi 60,0 s: entri lama sudah keluar
    assert state["sleeps"] == [60.0]


@pytest.mark.parametrize("raw", ["Tue, 27 Oct 2026 10:00:07", "Tue, 27 Oct 2026 10:00:07 GMT",
                                 "Tue, 27 Oct 2026 10:00:07 -0000"])
def test_S16_http_date_without_zone_is_utc(raw):
    now = datetime(2026, 10, 27, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    assert parse_retry_after(raw, now) == 7.0
