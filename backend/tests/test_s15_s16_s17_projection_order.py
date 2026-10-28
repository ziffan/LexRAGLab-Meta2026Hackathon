"""M3.2-effort-sweep (H-103 S3 bagian B): S15 faktor terukur (integer), S16 waktu Glimmer per effort + aturan reuse relatif,
S17 urutan termurah dulu, status complete/partial/not_run, pool habis di tengah, resume. Murni/transport palsu."""

import json

import pytest

from backend.header_b.compare import glimmer_time
from backend.proposal.gate import GateConfig, evaluate_gate, upper_bound
from backend.spark import ConfigInvalid, sweep_run

from .h101_helpers import GATE, make_prepared
from .sweep_b_helpers import args, run_main, sweep_cfg, sweep_rig
from .sweep_helpers import syn

PARAMS = {"prefill_tokens_per_s": 650, "base_ms": 4800, "output_tokens_per_10s": 237}
OPEN = "meta-models/muse-spark-open-1026"


# ------------------------------------------------------------------------------------------------ S15
def test_s15a_initial_factor_from_h101_ledger_over_project_only():
    assert sweep_run.ceil_factor_bp(14_075_194, 7_288_645) == 19_312
    assert 7_288_645 * 19_312 >= 140_751_940_000 > 7_288_645 * 19_311
    assert sweep_run.ceil_factor_bp(659_431, 441_820) == 14_926  # akta: informasi, tidak menaikkan
    assert sweep_run.effective_factor_bp(15_700, 16_553, 19_312) == 19_312


def test_s15b_pilot_with_all_retry_rounds():
    unit, warm = 19_125, 63_125
    assert (300 * 1_250_000 + 40_000 * 150_000 + 3_000 * 4_250_000) // 1_000_000 == unit
    assert (40_300 * 1_250_000 + 3_000 * 4_250_000) // 1_000_000 == warm
    rounds = [20 * unit + warm, 3 * unit + warm, unit + warm]
    assert rounds == [445_625, 120_500, 82_250] and sum(rounds) == 648_375
    expected = 20 * 8_288 + 52_288
    assert expected == 218_048
    measured = sweep_run.ceil_factor_bp(sum(rounds), expected)
    assert measured == 29_736 and 218_048 * 29_736 >= 6_483_750_000 > 218_048 * 29_735
    eff = sweep_run.effective_factor_bp(15_700, 19_312, measured)
    assert eff == 29_736
    assert upper_bound(881_088, eff) == 2_620_004
    assert upper_bound(881_088, 19_312) == 1_701_558 and upper_bound(881_088, 15_700) == 1_383_309


def test_s15c_control_contributor_pilot_does_not_lower_factor():
    assert 20 * 200 + 4_120 == 8_120
    assert 20 * 290 + 4_210 == 10_010
    measured = sweep_run.ceil_factor_bp(10_010, 8_120)
    assert measured == 12_328 and sweep_run.effective_factor_bp(15_700, None, measured) == 15_700


def test_s15e_expected_zero_is_config_invalid_not_division_by_zero():
    with pytest.raises(ConfigInvalid):
        sweep_run.ceil_factor_bp(100, 0)
    with pytest.raises(ConfigInvalid):
        sweep_run.ceil_factor_bp(-1, 10)


def test_s15e_pilot_over_gate_is_rejected_before_network(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    syn(rig.runs, "b", "baseten", OPEN, "xhigh", 49_999_999, rid="fill")  # pool sapuan hampir di ambang 50.000.000
    n0 = rig.tr.calls
    rc = run_main(rig, args("sweep_meta_medium", "--max-units", "3"), sweep=sw)
    assert rc == 1 and rig.tr.calls == n0  # gerbang menolak SEBELUM request (stopped = gate_rejected)
    rep = json.loads(next((rig.runs / "headers_compare" / "sweep_meta_medium" / "runs").glob("*.json")).read_text(encoding="utf-8"))
    assert rep["stopped"] == "gate_rejected" and rep["sweep"]["status"] == "not_run (pool)"
    assert rep["sweep"]["pool_remaining_micros"] == 50_000_000 - 49_999_999


# ------------------------------------------------------------------------------------------------ S16
@pytest.mark.parametrize("out,no_reuse,reuse", [
    (1_000, 41_079_395, 16_350_059), (1_800, 52_657_360, 27_928_024),
    (3_000, 70_024_479, 45_295_143), (4_500, 91_733_292, 67_003_956)])
def test_s16_glimmer_time_per_effort(out, no_reuse, reuse):
    t = glimmer_time(47_000, [300] * 343, out, PARAMS)
    assert (t["no_reuse_ms"], t["reuse_ms"]) == (no_reuse, reuse)


def test_s16_sum_of_four_efforts_and_out_tokens_default():
    rs = [glimmer_time(47_000, [300] * 343, o, PARAMS) for o in (1_000, 1_800, 3_000, 4_500)]
    assert sum(r["reuse_ms"] for r in rs) == 156_577_182 and sum(r["no_reuse_ms"] for r in rs) == 255_494_526
    sw = sweep_cfg()
    hc = {"max_output_tokens": 1000}
    assert sweep_run.out_tokens_for(hc, sw, "sweep_glimmer_medium") == 1000  # default = header_b max_output_tokens
    sw["projection"] = {"sweep_glimmer_medium": {"out_tokens": 1800}}
    assert sweep_run.out_tokens_for(hc, sw, "sweep_glimmer_medium") == 1800


def test_s16d_relative_reuse_rule_with_boundary():
    s = 72_770 - 462
    assert s == 72_308 and 150_000 - -(-s // 2) == 113_846
    ok = [150_000, 90_000, 100_000, 105_000, 140_000]
    assert sweep_run.reuse_confirmed_relative(ok, s) is True  # a + b = 205.000 <= 227.692
    assert sweep_run.reuse_confirmed_relative([150_000, 120_000, 130_000, 135_000, 160_000], s) is False  # 265.000
    assert sweep_run.reuse_confirmed_relative([150_000, 100_000, 113_846, 113_846, 200_000], s) is True  # 227.692
    assert sweep_run.reuse_confirmed_relative([150_000, 100_000, 113_846, 113_847, 200_000], s) is False  # 227.693
    assert sweep_run.reuse_confirmed_relative([150_000, 1, 2, 3], s) is None


def test_s16d_existing_threshold_rule_for_glimmer_local_is_unchanged():
    from backend.header_b.compare import reuse_confirmed
    assert reuse_confirmed([1, 59_000, 59_000, 61_000, 61_000]) is True and reuse_confirmed([1, 60_001, 60_001, 60_001, 60_001]) is False


# ------------------------------------------------------------------------------------------------ S17
def test_s17a_order_cheapest_first_within_model_and_models_by_d3():
    items = [{"profile": "sweep_meta_xhigh", "family": "meta", "effort": "xhigh", "total": 9_000_000},
             {"profile": "sweep_meta_medium", "family": "meta", "effort": "medium", "total": 3_000_000},
             {"profile": "sweep_meta_high", "family": "meta", "effort": "high", "total": 5_000_000},
             {"profile": "sweep_glimmer_medium", "family": "glimmer_local", "effort": "medium", "total": 0},
             {"profile": "sweep_baseten_high", "family": "baseten_open", "effort": "high", "total": 100}]
    got = [i["profile"] for i in sweep_run.sweep_order(items)]
    assert got == ["sweep_meta_medium", "sweep_meta_high", "sweep_meta_xhigh", "sweep_baseten_high", "sweep_glimmer_medium"]
    tie = [{"profile": "sweep_meta_xhigh", "family": "meta", "effort": "xhigh", "total": 3_000_000},
           {"profile": "sweep_meta_medium", "family": "meta", "effort": "medium", "total": 3_000_000}]
    assert [i["profile"] for i in sweep_run.sweep_order(tie)] == ["sweep_meta_medium", "sweep_meta_xhigh"]


def test_s17b_pool_exhausted_numbers_and_remaining():
    cfg = GateConfig(**GATE)
    thr = 50_000_000 * cfg.cumulative_pct // 100
    assert evaluate_gate([0], 38_005_250, cfg, upper_floor=1_977_750, threshold_micros=thr).ok  # 39.983.000
    v = evaluate_gate([0], 39_800_000, cfg, upper_floor=1_977_750, threshold_micros=thr)
    assert not v.ok and v.reasons == ("cumulative_over_threshold",) and 39_800_000 + 1_977_750 == 41_777_750
    assert 50_000_000 - 39_800_000 == 10_200_000


def test_s17d_status_strings():
    assert sweep_run.sweep_status(343, 343) == "complete"
    assert sweep_run.sweep_status(100, 343) == "partial (100/343 unit)"
    assert sweep_run.sweep_status(0, 343, pool_rejected=True) == "not_run (pool)"
    assert sweep_run.sweep_status(10, 343, pool_rejected=True) == "partial (10/343 unit)"


def test_s17c_resume_does_not_repeat_stored_units(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    assert run_main(rig, args("sweep_meta_medium"), sweep=sw, prepared=make_prepared(3)) == 0
    first = rig.tr.calls
    assert first >= 3
    out: list[str] = []
    assert run_main(rig, args("sweep_meta_medium"), sweep=sw, prepared=make_prepared(3), out=out) == 0
    assert rig.tr.calls == first and any("nothing to do" in ln for ln in out)
    rep = [json.loads(p.read_text(encoding="utf-8")) for p in (rig.runs / "headers_compare" / "sweep_meta_medium" / "runs").glob("*.json")]
    assert rep[0]["sweep"]["status"] == "complete"
