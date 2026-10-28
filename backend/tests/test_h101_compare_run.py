"""H-101 bagian 2 (skenario M3.2-open-weight-B S6-S9, S12, S14, S17): upaya ulang dan gagal jujur, proyeksi sadar-floor, pemecahan
batch, gerbang per pool dan per ronde, guard cache, RunRecord pembanding, proyeksi waktu Glimmer. Tanpa Model API."""

import json
from fractions import Fraction

import pytest

from backend.header_b import compare as cmp
from backend.header_b.compare import (batas_atas, call_ms, glimmer_time, prefill_ms, project_time_ms, reuse_confirmed,
                                      split_batches, unit_costs)
from backend.header_b.compare_store import CompareError, compare_store_dir
from backend.header_b.project import project_units
from backend.header_b.render import DocPrefix, WARM_UNIT, render_suffix
from backend.header_b.units import Unit
from backend.proposal.gate import GateConfig, evaluate_gate
from backend.spark import Ledger, store

from .h101_helpers import (GATE, PROMPT12, USAGE_BT, SizedTok, Tok, budget_b, hc_b, make_prepared, model_b, rig_for, words)
from .h101_run import go
from .spark_fakes import synth

BT = {"input": 1_250_000, "cached": 150_000, "output": 4_250_000}
META = {"input": 100_000, "cached": 2_000, "output": 200_000}
KW = dict(expected_output_tokens=450, max_output_tokens=1000, warm_max_output_tokens=1000)


def rejected_count(d, cid):
    return len(list((d / "pasal" / PROMPT12 / "rejected").glob(f"{cid}.*.json")))


# ------------------------------------------------------------------------------------------------ S6
S6 = {"CH-U2": [words(41), words(41), "ok dua"], "CH-U3": [words(41)], "CH-U4": ["EMPTY", "ok empat"]}


def test_s6_baseten_eight_attempts_honest_failure_no_fallback(tmp_path):
    log: list[str] = []
    rig = rig_for(tmp_path, "baseten_open", S6, log=log)
    d = compare_store_dir(rig.runs, "baseten_open")
    s = go(rig, make_prepared(4), d, max_attempts=8)
    assert log.count("warmup") == 8 and len(log) - 8 == 14 and rig.tr.calls == 22  # 4+3+2+5 panggilan unit + 1 pemanas per ronde
    assert s["attempts"] == {"uupt-x/pasal": 8} and s["failed"] == {"uupt-x/pasal": ["CH-U3"]} and s["stopped"] is None
    stored = sorted(p.stem for p in (d / "pasal" / PROMPT12).glob("*.json"))
    assert stored == ["CH-U1", "CH-U2", "CH-U4"] and s["stored"] == 3
    assert (rejected_count(d, "CH-U2"), rejected_count(d, "CH-U3"), rejected_count(d, "CH-U4")) == (2, 8, 1)
    assert not (d / "pasal" / PROMPT12 / "CH-U3.json").exists()  # tanpa fallback ke header lain
    assert not (rig.runs / "headers").exists()


def test_s6_control_three_attempts_glimmer_no_warmup_and_baseten_with(tmp_path):
    log: list[str] = []
    rig = rig_for(tmp_path / "g", "glimmer_local", S6, log=log)
    d = compare_store_dir(rig.runs, "glimmer_local")
    s = go(rig, make_prepared(4), d, profile="glimmer_local", max_attempts=3)
    assert rig.tr.calls == 9 and "warmup" not in log and s["warm"] is False  # 4+3+2, pemanas 0
    assert sorted(p.stem for p in (d / "pasal" / PROMPT12).glob("*.json")) == ["CH-U1", "CH-U2", "CH-U4"]
    assert (rejected_count(d, "CH-U2"), rejected_count(d, "CH-U3"), rejected_count(d, "CH-U4")) == (2, 3, 1) and s["failed"] == {"uupt-x/pasal": ["CH-U3"]}
    log2: list[str] = []
    rig2 = rig_for(tmp_path / "b", "baseten_open", S6, log=log2)
    go(rig2, make_prepared(4), compare_store_dir(rig2.runs, "baseten_open"), max_attempts=3)
    assert rig2.tr.calls == 12 and log2.count("warmup") == 3  # 9 + 3 pemanas


# ------------------------------------------------------------------------------------------------ S7
def costs(pricing, floor, n=100, warm=True):
    return unit_costs(40_000, [300] * n, 300, pricing, floor=floor, warm=warm, **KW)


def test_s7_baseten_floor_aware_upper_bound_numbers():
    c = costs(BT, 6000)
    assert (c["unit_expected"][0], c["warm_expected"]) == (8288, 52288) and c["expected"] == 881_088
    assert batas_atas(881_088, 0, 15700, False) == 1_383_309
    old = costs(BT, None)
    assert (old["unit_upper_cached"][0], old["warm_upper"], old["upper_cached"]) == (10_625, 54_625, 1_117_125)
    assert old["upper_no_cache"] == 5_517_125
    assert (c["unit_upper_cached"][0], c["warm_upper"], c["upper_cached"]) == (31_875, 75_875, 3_263_375)
    assert c["upper_no_cache"] == 7_663_375
    # rumus lama meloloskan (salah); sadar-floor menolak dengan batas atas 3.263.375
    cfg = GateConfig(**GATE)
    old_v = evaluate_gate(old["unit_expected"] + [old["warm_expected"]], 0, cfg)
    assert old_v.ok and old_v.batas_atas == 1_383_309
    v = evaluate_gate(c["unit_expected"] + [c["warm_expected"]], 0, cfg, upper_floor=c["upper_cached"])
    assert not v.ok and v.batas_atas == 3_263_375 and v.reasons == ("batas_atas_over_batch_cap",)
    assert batas_atas(c["expected"], c["upper_cached"], 15700, True) == 3_263_375


def test_s7_contributor_without_floor_is_unchanged():
    c = costs(META, None)
    assert (c["unit_expected"][0], c["warm_expected"], c["expected"]) == (200, 4120, 24_120)
    assert batas_atas(24_120, c["upper_cached"], 15700, False) == 37_869
    assert (c["upper_cached"], c["upper_no_cache"]) == (35_230, 427_230)
    # identik dengan proyeksi M3.1 yang sudah ada (`project_units`) untuk profil tanpa floor
    class Const:
        def count(self, text):
            return 300
    prefix = DocPrefix("x", "n", 40_000, "k")
    units = [Unit(f"c{i}", "a", "t", 1, (f"c{i}",)) for i in range(100)]
    ref = project_units(units, prefix, Const(), META, rpm=140, assumed_latency_ms=3000, **KW)["cost_usd_micros"]
    assert (ref["expected"], ref["upper_cached"], ref["upper_no_cache"]) == (c["expected"], c["upper_cached"], c["upper_no_cache"])


def test_s7_glimmer_zero_price_gate_always_passes():
    z = {"input": 0, "cached": 0, "output": 0}
    c = costs(z, 16_000)
    assert c["expected"] == c["upper_cached"] == c["upper_no_cache"] == 0
    assert evaluate_gate(c["unit_expected"], 0, GateConfig(**GATE), upper_floor=0).ok


# ------------------------------------------------------------------------------------------------ S8
def test_s8_batch_split_numbers():
    ca = costs(BT, 6000, n=130)
    ids = [f"A{i}" for i in range(130)]
    idx = split_batches(ids, ca, batch_cap=2_000_000, factor_bp=15700)
    assert [len(b) for b in idx] == [60, 60, 10]
    assert [sum(ca["unit_upper_cached"][i] for i in b) + ca["warm_upper"] for b in idx] == [1_988_375, 1_988_375, 394_625]
    cb = costs(BT, 6000, n=20)
    ib = split_batches([f"B{i}" for i in range(20)], cb, batch_cap=2_000_000, factor_bp=15700)
    assert [len(b) for b in ib] == [20] and cb["upper_cached"] == 713_375
    assert 1_988_375 + 1_988_375 + 394_625 + 713_375 == 5_084_750
    assert split_batches(ids, ca, batch_cap=1_988_375, factor_bp=15700)[0] == list(range(60))  # inklusif
    assert len(split_batches(ids, ca, batch_cap=1_988_374, factor_bp=15700)[0]) == 59  # 59 x 31.875 + 75.875 = 1.956.500
    assert [len(b) for b in split_batches(ids[:5], costs(BT, 6000, n=5), batch_cap=140_000, factor_bp=15700)] == [2, 2, 1]
    assert 2 * 31_875 + 75_875 == 139_625 and 3 * 31_875 + 75_875 == 171_500


def test_s8_unit_over_batch_cap_names_the_unit_and_figure():
    c = costs(BT, 6000, n=3)
    with pytest.raises(CompareError) as ei:
        split_batches(["CH-U1", "CH-U2", "CH-U3"], c, batch_cap=90_000, factor_bp=15700)
    assert ei.value.code == "unit_over_batch_cap" and "CH-U1" in str(ei.value) and "107750" in str(ei.value)


def sized(n):
    return make_prepared(n, tok=SizedTok())


def test_s8_run_rejects_whole_run_before_any_request(tmp_path):
    rig = rig_for(tmp_path, "baseten_open")
    d = compare_store_dir(rig.runs, "baseten_open")
    with pytest.raises(CompareError) as ei:
        go(rig, sized(3), d, tokenizer=SizedTok(), gate_cfg={"batch_cap_micros": 90_000})
    assert ei.value.code == "unit_over_batch_cap" and rig.tr.calls == 0 and not d.exists()


def test_s8_run_splits_into_batches_each_with_one_warmup(tmp_path):
    log: list[str] = []
    rig = rig_for(tmp_path, "baseten_open", log=log)
    d = compare_store_dir(rig.runs, "baseten_open")
    s = go(rig, sized(5), d, tokenizer=SizedTok(), gate_cfg={"batch_cap_micros": 140_000})
    assert [b["units"] for b in s["batches"]] == [2, 2, 1] and [b["upper_cached"] for b in s["batches"]] == [139_625, 139_625, 107_750]
    assert log.count("warmup") == 3 and rig.tr.calls == 8 and s["stored"] == 5
    order = [c for c in log]
    assert order == ["warmup", "CH-U1", "CH-U2", "warmup", "CH-U3", "CH-U4", "warmup", "CH-U5"]  # urutan dokumen, tak dipindah


# ------------------------------------------------------------------------------------------------ S9
def gate_for(rig):
    return cmp.make_gate("baseten", rig.budget, rig.model, rig.env, rig.runs)


def seed(rig, provider, cost, role="c", n=0):
    synth(rig.runs, role, provider, cost, run_id=f"seed-{provider}-{role}-{cost}-{n}")


def test_s9_cumulative_per_pool_inclusive_and_pool_control(tmp_path):
    rig = rig_for(tmp_path, "baseten_open")
    seed(rig, "baseten", 14_011_625)
    g = gate_for(rig)
    assert g([0], 1_988_375).ok  # 14.011.625 + 1.988.375 = 16.000.000 (inklusif)
    seed(rig, "baseten", 1, n=1)
    v = g([0], 1_988_375)
    assert not v.ok and v.reasons == ("cumulative_over_threshold",)
    rig2 = rig_for(tmp_path / "c", "baseten_open")
    seed(rig2, "baseten", 14_011_625)
    for i, (role, c) in enumerate((("a", 8_170), ("b", 526_265), ("c", 5_964), ("d", 21_342))):
        seed(rig2, "meta", c, role, i)  # pool default 561.741 tidak ikut
    assert gate_for(rig2)([0], 1_988_375).ok


def test_s9_threshold_comes_from_provider_cap_not_cumulative_cap(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", budget=budget_b(provider_cap_micros={"baseten": 10_000_000}))
    seed(rig, "baseten", 6_011_625)
    g = gate_for(rig)
    assert g([0], 1_988_375).ok  # 6.011.625 + 1.988.375 = 8.000.000 = 10.000.000 x 80%
    seed(rig, "baseten", 1, n=1)
    assert not g([0], 1_988_375).ok  # akan lolos bila memakai cumulative_cap_micros (16.000.000)


def test_s9_gate_per_round_stops_run_without_requests_for_round_two(tmp_path):
    cfg = GateConfig(**GATE)

    def run(spent_after_round1):
        log: list[str] = []
        rig = rig_for(tmp_path / str(spent_after_round1), "baseten_open", {"CH-U2": [words(41)], "CH-U3": [words(41)], "CH-U4": [words(41)]}, log=log)
        d = compare_store_dir(rig.runs, "baseten_open")
        calls = []

        def gate(expected, floor):
            calls.append(floor)
            return evaluate_gate(expected, 0 if len(calls) == 1 else spent_after_round1, cfg, upper_floor=floor, threshold_micros=16_000_000)

        s = go(rig, sized(4), d, tokenizer=SizedTok(), gate=gate, max_attempts=8)
        return s, calls, rig, d

    s, calls, rig, d = run(15_828_500)  # 15.828.500 + 171.500 = 16.000.000: ronde 2 jalan
    assert calls[:2] == [4 * 31_875 + 75_875, 3 * 31_875 + 75_875] and len(calls) == 8
    s2, calls2, rig2, d2 = run(15_828_501)  # ditolak
    assert s2["stopped"] == "gate_rejected" and len(calls2) == 2 and rig2.tr.calls == 5  # hanya ronde 1: 1 pemanas + 4 unit
    assert s2["failed"] == {"uupt-x/pasal": ["CH-U2", "CH-U3", "CH-U4"]} and s2["stored"] == 1
    assert [p.stem for p in (d2 / "pasal" / PROMPT12).glob("*.json")] == ["CH-U1"]


def test_s9e_contributor_gate_ignores_baseten_spend_only_with_provider_table(tmp_path):
    rig = rig_for(tmp_path, "baseten_open")
    for i, (role, c) in enumerate((("a", 8_170), ("b", 526_265), ("c", 5_964), ("d", 21_342))):
        seed(rig, "meta", c, role, i)
    seed(rig, "baseten", 93_751, "a")
    seed(rig, "baseten", 53_267, "c", 1)
    from backend.proposal.gate import cumulative_threshold_for, load_gate_config
    from backend.spark.budget import effective_caps
    caps = effective_caps(rig.budget, None, rig.model).provider_micros
    led = Ledger(rig.runs)
    assert led.spent_pool("meta", caps) == 561_741 and led.spent() == 708_759 and led.spent_pool("baseten", caps) == 147_018
    assert cumulative_threshold_for("meta", rig.budget, caps) == 16_000_000
    no_table = budget_b()
    del no_table["provider_cap_micros"]
    no_table["version"] = 1
    assert led.spent_pool("meta", effective_caps(no_table, None, rig.model).provider_micros) == 708_759  # kembali ke total ledger


# ------------------------------------------------------------------------------------------------ S12
def usage_seq(cached_by_call, inp=47_500):
    return lambda k: {"input_tokens": inp, "input_tokens_details": {"cached_tokens": cached_by_call(k)}, "output_tokens": 50,
                      "output_tokens_details": {"reasoning_tokens": 10}}


def test_s12a_exactly_four_fifths_continues(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", usage=usage_seq(lambda k: 38_000))
    s = go(rig, make_prepared(12), compare_store_dir(rig.runs, "baseten_open"))
    assert s["stopped"] is None and s["stored"] == 12 and s["cache_guard"] == "active" and rig.tr.calls == 13  # + 1 pemanas


def test_s12b_just_below_four_fifths_stops_after_tenth_keeping_its_header(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", usage=usage_seq(lambda k: 38_000 if k < 9 else 37_999))
    d = compare_store_dir(rig.runs, "baseten_open")
    s = go(rig, make_prepared(12), d)
    assert s["stopped"] == "cache_ratio_low" and s["stored"] == 10 and rig.tr.calls == 11
    assert sorted(p.stem for p in (d / "pasal" / PROMPT12).glob("*.json")) == sorted(f"CH-U{i}" for i in range(1, 11))


def test_s12c_glimmer_skips_guard_but_keeps_error_stop(tmp_path):
    rig = rig_for(tmp_path, "glimmer_local", chat_usage={"prompt_tokens": 47_500, "cached": 0, "completion_tokens": 50})
    s = go(rig, make_prepared(12), compare_store_dir(rig.runs, "glimmer_local"), profile="glimmer_local")
    assert s["stopped"] is None and s["stored"] == 12 and rig.tr.calls == 12 and s["cache_guard"] == "skipped"
    bad = {f"CH-U{i}": [words(41)] for i in range(1, 13)}
    rig2 = rig_for(tmp_path / "e", "glimmer_local", bad)
    s2 = go(rig2, make_prepared(12), compare_store_dir(rig2.runs, "glimmer_local"), profile="glimmer_local",
            hc=hc_b(max_consecutive_errors=5), max_attempts=3)
    assert s2["stopped"] == "too_many_errors" and rig2.tr.calls == 5


def test_s12d_local_cache_hits_do_not_count_for_the_guard(tmp_path):
    rig = rig_for(tmp_path, "baseten_open", usage=usage_seq(lambda k: 38_000))
    go(rig, make_prepared(12), compare_store_dir(rig.runs, "baseten_open"))
    n = rig.tr.calls
    s = go(rig, make_prepared(12), compare_store_dir(rig.runs, "baseten_open") / "second")  # store lain: 12 cache hit klien
    assert rig.tr.calls == n + 1 and s["stopped"] is None and s["stored"] == 12  # hanya pemanas yang dikirim


# ------------------------------------------------------------------------------------------------ S14
def test_s14_run_records_carry_profile_identity_and_cost(tmp_path):
    u = {"input_tokens": 47_500, "input_tokens_details": {"cached_tokens": 38_000}, "output_tokens": 700,
         "output_tokens_details": {"reasoning_tokens": 600}}
    rig = rig_for(tmp_path, "baseten_open", usage=u)
    go(rig, make_prepared(1), compare_store_dir(rig.runs, "baseten_open"))
    recs = [r for r in store.load_records(rig.runs) if r.kind == "spark_b" and r.prompt_hash == "a" * 64 or r.kind == "spark_b"]
    unit = [r for r in recs if r.cost_usd_micros == 20_550]
    assert unit and (9_500 * 1_250_000 + 38_000 * 150_000 + 700 * 4_250_000) == 20_550 * 1_000_000 - 0
    r = unit[0]
    assert (r.provider, r.model, r.quantization, r.effort, r.kind) == ("baseten", "meta-models/muse-spark-open-1026", None, "low", "spark_b")
    gl = rig_for(tmp_path / "g", "glimmer_local")
    go(gl, make_prepared(1), compare_store_dir(gl.runs, "glimmer_local"), profile="glimmer_local")
    (g,) = [r for r in store.load_records(gl.runs) if r.kind == "spark_b"]
    assert (g.provider, g.model, g.quantization, g.effort, g.cost_usd_micros, g.device) == (
        "lmstudio_local", "meta/muse-glimmer", "Q4_K_M", "high", 0, "local")
    assert g.provider != "meta"


def test_s14d_ledger_provider_sum_and_glimmer_adds_zero(tmp_path):
    rig = rig_for(tmp_path, "baseten_open")
    seed(rig, "baseten", 100, "a")
    seed(rig, "baseten", 200, "b", 1)
    seed(rig, "baseten", 300, "c", 2)
    seed(rig, "lmstudio_local", 0, "b", 3)
    led = Ledger(rig.runs)
    assert led.spent(provider="baseten") == 600 and led.spent(provider="lmstudio_local") == 0 and led.spent() == 600


def test_s14e_cache_key_differs_by_effort(tmp_path):
    keys = []
    for eff in ("high", "medium"):
        m = model_b()
        m["profiles"]["glimmer_local"]["reasoning_effort"] = eff
        rig = rig_for(tmp_path / eff, "glimmer_local", model=m)
        go(rig, make_prepared(1), compare_store_dir(rig.runs, "glimmer_local"), profile="glimmer_local")
        keys.append([r.cache_key for r in store.load_records(rig.runs) if r.kind == "spark_b"][0])
    assert keys[0] != keys[1]


# ------------------------------------------------------------------------------------------------ S15 (c)
def test_s15c_comparison_records_are_not_reportable(tmp_path):
    from backend.spark import NotReportable, require_reportable
    rig = rig_for(tmp_path, "baseten_open")
    go(rig, make_prepared(1), compare_store_dir(rig.runs, "baseten_open"))
    recs = store.load_records(rig.runs)
    assert recs
    with pytest.raises(NotReportable):
        require_reportable(recs)
    synth(rig.runs, "b", "meta", 5, run_id="meta-ok")
    require_reportable([r for r in store.load_records(rig.runs) if r.provider == "meta"])


# ------------------------------------------------------------------------------------------------ S17
P = {"prefill_tokens_per_s": 650, "base_ms": 4800, "output_tokens_per_10s": 237}


def test_s17a_b_time_numbers_and_projection_uses_profile_parameters():
    assert prefill_ms(300, P) == 462 and cmp.output_ms(1000, P) == 42_195
    assert call_ms(73_000, 1000, P) == 119_995 and call_ms(prefill_ms(300, P), 1000, P) == 47_457
    t = project_time_ms(343, 119_995, 47_457)
    assert t == {"no_reuse_ms": 41_158_285, "reuse_ms": 16_350_289}
    assert project_time_ms(344, 119_995, 47_457) == {"no_reuse_ms": 41_278_280, "reuse_ms": 16_397_746}  # alternatif Q-B11
    # turunan dari parameter config (650 tok/s): prefiks 47.000 + suffix 300 = 47.300 token -> ceil(47.300 x 1000 / 650) = 72.770 ms
    g = glimmer_time(47_000, [300] * 3, 1000, P)
    first = 72_770 + 4_800 + 42_195
    assert g["no_reuse_ms"] == 3 * first and g["reuse_ms"] == first + 2 * 47_457 and g["calls"] == 3
    assert "assumed_latency" not in json.dumps(g) and "no_reuse" in g["basis"]


@pytest.mark.parametrize("lat,want", [([60_000, 41_000, 47_000, 52_000, 70_000], True), ([60_000, 41_000, 61_000, 65_000, 70_000], False),
                                      ([1, 60_000, 60_000, 60_000, 60_000], True), ([1, 60_000, 60_001, 60_001, 60_002], False),
                                      ([1, 2, 3], None)])
def test_s17c_reuse_smoke_median_of_calls_two_to_five(lat, want):
    assert reuse_confirmed(lat) is want  # contoh spec: median (47.000 + 52.000)/2 = 49.500 <= 60.000; 63.000 > 60.000


def test_s17e_resume_after_interrupt_and_sample_counts_unstored_only(tmp_path):
    def fresh(tag):
        rig = rig_for(tmp_path / tag, "glimmer_local")
        d = compare_store_dir(rig.runs, "glimmer_local")
        from .h101_helpers import put_header
        for i in range(1, 5):
            put_header(d, "pasal", f"CH-U{i}", f"Header lama {i}")
        return rig, d

    rig, d = fresh("a")
    s = go(rig, make_prepared(10), d, profile="glimmer_local")
    assert rig.tr.calls == 6 and len(list((d / "pasal" / PROMPT12).glob("*.json"))) == 10 and s["stopped"] is None
    assert json.loads((d / "pasal" / PROMPT12 / "CH-U1.json").read_text(encoding="utf-8"))["header"] == "Header lama 1"  # tak ditimpa
    rig, d = fresh("b")
    go(rig, make_prepared(10), d, profile="glimmer_local", sample=3)
    assert rig.tr.calls == 3 and sorted(p.stem for p in (d / "pasal" / PROMPT12).glob("*.json"))[-3:] == ["CH-U5", "CH-U6", "CH-U7"]
    go(rig, make_prepared(10), d, profile="glimmer_local", max_units=2)  # pilot: 2 unit pertama yang belum tersimpan
    assert rig.tr.calls == 5 and (d / "pasal" / PROMPT12 / "CH-U9.json").is_file() and not (d / "pasal" / PROMPT12 / "CH-U10.json").exists()


def test_s17f_timeout_is_a_failed_round_and_retried_in_next_round(tmp_path):
    rig = rig_for(tmp_path, "glimmer_local", {"CH-U3": ["TIMEOUT", "Header sah tiga"]})
    d = compare_store_dir(rig.runs, "glimmer_local")
    s = go(rig, make_prepared(5), d, profile="glimmer_local", max_attempts=3)
    assert rig.tr.calls == 5 + 1 and s["failed"] == {} and s["stopped"] is None and len(list((d / "pasal" / PROMPT12).glob("*.json"))) == 5
    errs = [r for r in store.load_records(rig.runs) if r.status == "error"]
    assert len(errs) == 1 and errs[0].error["code"] == "timeout" and errs[0].latency_ms == 900_000  # tepat timeout_s, tanpa retry dalam ronde
    assert [b["called"] for b in s["batches"]] == [5, 1]
