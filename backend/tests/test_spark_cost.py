"""M0.1 S1-S6, S39: biaya integer micro-USD, harga dari config, usage rusak, lokasi cached_tokens.
Skenario: docs/scenarios/M0.1.md. Transport palsu; nol jaringan."""

import json

import pytest

from backend.spark import ConfigInvalid, Ledger, compute_cost_micros, format_usd_micros
from backend.spark.errors import UsageInvalid
from backend.tests.spark_fakes import (
    USAGE1,
    USAGE2,
    Resp,
    Rig,
    body_ok,
    call_args,
    model_cfg,
)

P = {"input": 100000, "cached": 2000, "output": 200000}


def test_S01_cost_real_call_1_uncached(tmp_path):
    rig = Rig(tmp_path)
    res = rig.client.call(**call_args(0))
    r = res.record
    assert r.status == "ok" and r.error is None
    assert r.cost_usd_micros == 414 and type(r.cost_usd_micros) is int
    assert (r.usage_input_tokens, r.usage_cached_tokens, r.usage_output_tokens) == (3247, 0, 445)
    assert '"cost_usd_micros":414,' in r.to_json()  # int di JSON, bukan 414.0
    assert compute_cost_micros({"input": 3247, "cached": 0, "output": 445}, P) == 414


def test_S02_cost_real_call_2_cached_prefix_and_sum(tmp_path):
    rig = Rig(tmp_path, script=[Resp(200, body_ok(usage=USAGE1)), Resp(200, body_ok(usage=USAGE2))])
    r1 = rig.client.call(**call_args(1)).record
    r2 = rig.client.call(**call_args(2)).record
    assert rig.tr.calls == 2  # kunci cache hasil beda -> #2 tidak dilayani dari cache
    assert r1.cost_usd_micros == 414
    assert r2.usage_cached_tokens == 3185 and r2.cost_usd_micros == 103
    assert Ledger(rig.runs).spent() == 517
    assert [q["body"]["prompt_cache_key"] for q in rig.tr.requests] == ["pck-synth-1", "pck-synth-1"]


@pytest.mark.parametrize("usage,expected", [
    ((70, 0, 0), 7), ((10, 0, 0), 1), ((20, 0, 0), 2), ((40, 0, 0), 4), ((80, 0, 0), 8),
    ((5, 0, 0), 1), ((25, 0, 0), 3), ((1000, 0, 1), 101), ((1, 0, 0), 1), ((0, 0, 0), 0),
    ((1, 1, 0), 1), ((1_000_000, 1_000_000, 1_000_000), 202000), ((1_000_000, 0, 1_000_000), 300000),
    ((3185, 3185, 0), 7), ((0, 0, 1), 1),
])
def test_S03_rounding_table(usage, expected):
    i, c, o = usage
    got = compute_cost_micros({"input": i, "cached": c, "output": o}, P)
    assert got == expected and type(got) is int


def test_S04_pricing_read_from_config_not_constants(tmp_path):
    big = {"input": 200000, "cached": 4000, "output": 400000}
    assert compute_cost_micros({"input": 3247, "cached": 0, "output": 445}, big) == 828
    assert compute_cost_micros({"input": 3247, "cached": 3185, "output": 452}, big) == 206
    third = {"input": 100000, "cached": 20000, "output": 200000}
    assert compute_cost_micros({"input": 3247, "cached": 3185, "output": 452}, third) == 161
    # end-to-end: harga config berubah -> biaya record berubah
    m = model_cfg()
    m["pricing"]["meta"] = {"input_per_mtok_micros": 200000, "cached_per_mtok_micros": 4000,
                            "output_per_mtok_micros": 400000}
    rig = Rig(tmp_path, model=m)
    assert rig.client.call(**call_args(0)).record.cost_usd_micros == 828


def test_S04_profile_without_pricing_block_is_config_invalid_before_network(tmp_path):
    m = model_cfg()
    del m["pricing"]["meta"]
    with pytest.raises(ConfigInvalid):
        Rig(tmp_path, model=m)
    m2 = model_cfg()
    m2["pricing"]["meta"]["cached_per_mtok_micros"] = 0.002  # float tidak diterima
    with pytest.raises(ConfigInvalid):
        Rig(tmp_path, model=m2)


@pytest.mark.parametrize("label,usage", [
    ("a_cached_gt_input", {"input_tokens": 5, "input_tokens_details": {"cached_tokens": 6}, "output_tokens": 1}),
    ("b_negative_input", {"input_tokens": -1, "output_tokens": 1}),
    ("c_missing_output", {"input_tokens": 10}),
    ("d_missing_usage", None),
    ("e_float_input", {"input_tokens": 3247.5, "output_tokens": 1}),
    ("f_string_input", {"input_tokens": "3247", "output_tokens": 1}),
])
def test_S05_usage_invalid(tmp_path, label, usage):
    rig = Rig(tmp_path, script=[Resp(200, body_ok(usage=usage))])
    res = rig.client.call(**call_args(0, est_input=3000, max_output_tokens=500))
    r = res.record
    assert r.status == "error" and r.error["code"] == "usage_invalid"
    assert r.cost_usd_micros is None
    assert r.projected_cost_usd_micros == 400  # cabang A (O-3)
    assert res.output is None
    assert not list((rig.runs / "spark" / "c").glob("*.json"))  # tidak ada entri cache
    assert "\n" not in r.error["message"] and "Traceback" not in r.error["message"]
    d = json.loads(r.to_json())
    assert all(not isinstance(v, float) for v in d.values())
    assert (d["usage_input_tokens"], d["usage_cached_tokens"], d["usage_output_tokens"]) == (None, None, None)
    assert Ledger(rig.runs).spent() == 400  # dibaca dari disk (instance baru)


def test_S05_usage_helpers_reject_bad_values():
    for bad in ({"input": -1, "cached": 0, "output": 0}, {"input": 5, "cached": 6, "output": 0},
                {"input": 1.5, "cached": 0, "output": 0}, {"input": True, "cached": 0, "output": 0},
                {"input": 1, "cached": 0}):
        with pytest.raises(UsageInvalid):
            compute_cost_micros(bad, P)


@pytest.mark.parametrize("details", [
    {"__none__": True},  # tanpa input_tokens_details sama sekali
    {"input_tokens_details": {"cached_tokens": None}},
    {"input_tokens_details": {}},
])
def test_S06_cached_tokens_location(tmp_path, details):
    usage = {"input_tokens": 3247, "output_tokens": 452, "prompt_tokens_details": {"cached_tokens": 999}}
    if "input_tokens_details" in details:
        usage["input_tokens_details"] = details["input_tokens_details"]
    rig = Rig(tmp_path, script=[Resp(200, body_ok(usage=usage))])
    r = rig.client.call(**call_args(0)).record
    assert r.status == "ok"
    assert r.usage_cached_tokens == 0 and r.cost_usd_micros == 416


@pytest.mark.parametrize("micros,text", [
    (0, "$0.000000"), (1, "$0.000001"), (414, "$0.000414"), (517, "$0.000517"), (202000, "$0.202000"),
    (1_000_000, "$1.000000"), (1_234_567, "$1.234567"), (2_000_000, "$2.000000"),
])
def test_S39_format_usd_micros(micros, text):
    assert format_usd_micros(micros) == text


def test_S39_format_rejects_float_and_negative():
    with pytest.raises(TypeError):
        format_usd_micros(414.0)
    with pytest.raises(ValueError):
        format_usd_micros(-1)
