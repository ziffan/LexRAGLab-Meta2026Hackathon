"""M3.2-effort-sweep S4 (pool sapuan 50M, aturan off-pin), S6 (gerbang G-36 dan pemecahan batch), S9 (gerbang laporan),
S19 (k)(l) (pergeseran pool pada ledger nyata, per pemanggil), kenari S8 (h1)(h2)(o). Angka persis skenario."""

import re
from pathlib import Path

import pytest

from backend.header_b import compare as cmp
from backend.proposal.gate import cumulative_threshold_for, evaluate_gate, load_gate_config, sweep_threshold_micros
from backend.spark.sweep import validate_sweep
from backend.spark import (BudgetExceeded, ConfigInvalid, Ledger, NotReportable, budget as budget_mod, effective_caps,
                           pool_limits, require_reportable)
from backend.spark.budget import is_off_pin
from backend.spark.store import load_records

from .m25_fakes import env_m25
from .sweep_helpers import CONTRIB, GLIM, OPEN, calls_for_total, cfgs, f3, make_client, project_total, syn

BT = {"input": 1_250_000, "cached": 150_000, "output": 4_250_000}
META = {"input": 100_000, "cached": 2_000, "output": 200_000}


@pytest.fixture
def world(tmp_path):
    m, b, s = cfgs()
    f3(tmp_path / "runs")
    return m, b, s, tmp_path


# ------------------------------------------------------------------ S4 (h)(g)
def test_s4_h_ledger_pools_f3(world):
    m, b, s, tmp = world
    led = Ledger(tmp / "runs")
    caps = effective_caps(b, None, m)
    pc = caps.provider_micros
    assert led.spent_pool("meta", pc, model_cfg=m) == 561_741
    assert led.spent_pool("baseten", pc, model_cfg=m) == 15_513_750
    assert led.spent_off_pin(model_cfg=m) == 38_005_250
    assert led.spent() == 54_080_741 == 561_741 + 15_513_750 + 38_005_250
    assert led.spent_pool("meta", pc, "b", model_cfg=m) == 526_265
    for fn, a in ((led.spent_pool, ("meta", pc)), (led.spent_off_pin, ()), (pool_limits, (led, caps, "meta", "b"))):
        with pytest.raises(TypeError):
            fn(*a)


def test_s4_g_projection_fields_and_pool_label(world):
    m, b, s, tmp = world
    c, tr = make_client(tmp, "sweep_baseten_high")
    p = project_total(c, "b", [100])
    assert (p.pool, p.pool_cap_micros, p.pool_spent_micros) == ("sweep", 75_000_000, 38_005_250)
    main, _ = make_client(tmp, "baseten_open")
    q = project_total(main, "b", [100])
    assert (q.pool, q.pool_cap_micros, q.pool_spent_micros) == ("baseten", 20_000_000, 15_513_750)


# ------------------------------------------------------------------ S4 (a)(b)(c)(d)(e)
def test_s4_a_client_guard_boundary_inclusive(world):
    m, b, s, tmp = world
    c, tr = make_client(tmp, "sweep_baseten_high")
    ests = calls_for_total(36_994_750, BT, 12_000)
    p = project_total(c, "b", ests)
    assert p.total_micros == 36_994_750 and p.verdict == "ok"
    ests = calls_for_total(36_994_751, BT, 12_000)
    p = project_total(c, "b", ests)
    assert p.total_micros == 36_994_751 and p.verdict == "budget_exceeded"
    for needle in ("sweep", "38005250", "36994751", "75000000"):
        assert needle in p.reason
    with pytest.raises(BudgetExceeded):
        c.run_batch([dict(role="b", prompt_version="v", prompt_hash="P", input=f"x{i}", schema={}, schema_name="S",
                          schema_hash="S", prompt_cache_key=None, max_output_tokens=1, est_input=e)
                     for i, e in enumerate(ests)])
    assert tr.calls == 0


def test_s4_b_role_and_total_caps_do_not_apply_in_sweep_pool(world):
    m, b, s, tmp = world
    c, _ = make_client(tmp, "sweep_meta_high")
    p = project_total(c, "b", [1])
    assert p.verdict == "ok" and p.pool == "sweep" and p.pool_spent_micros == 38_005_250  # >> cap peran b 1.000.000


def test_s4_c_full_sweep_pool_does_not_block_other_pools(world):
    m, b, s, tmp = world
    syn(tmp / "runs", "c", "baseten", OPEN, "xhigh", 36_994_750, rid="fill-sweep")
    assert Ledger(tmp / "runs").spent_off_pin(model_cfg=m) == 75_000_000
    bt, _ = make_client(tmp, "baseten_open")
    ok = project_total(bt, "b", calls_for_total(4_486_250, BT, 6_000))
    no = project_total(bt, "b", calls_for_total(4_486_251, BT, 6_000))
    assert (ok.verdict, no.verdict) == ("ok", "budget_exceeded") and ok.pool == "baseten"
    mt, _ = make_client(tmp, "meta")
    ok = project_total(mt, "d", calls_for_total(228_658, META, 1))
    no = project_total(mt, "d", calls_for_total(228_659, META, 1))
    assert (ok.verdict, no.verdict) == ("ok", "budget_exceeded") and "role d cap" in no.reason
    sw, _ = make_client(tmp, "sweep_meta_high")
    assert project_total(sw, "b", [1]).verdict == "budget_exceeded"  # pool sapuan sendiri penuh


def test_s4_c_sweep_pool_exactly_full_rejects_positive_projection(world):
    m, b, s, tmp = world
    syn(tmp / "runs", "c", "baseten", OPEN, "xhigh", 36_994_750, rid="fill-sweep")
    sw, _ = make_client(tmp, "sweep_glimmer_low")  # biaya 0: proyeksi 0 lolos walau pool penuh
    assert project_total(sw, "b", [100]).verdict == "ok"
    sm, _ = make_client(tmp, "sweep_meta_high")
    assert project_total(sm, "b", [100]).verdict == "budget_exceeded"


def test_s4_d_other_pools_full_do_not_block_sweep(world):
    m, b, s, tmp = world
    syn(tmp / "runs", "c", "baseten", OPEN, "low", 4_486_250, rid="on-pin-bt")
    syn(tmp / "runs", "d", "meta", CONTRIB, "low", 1_438_259, rid="on-pin-meta")
    led = Ledger(tmp / "runs")
    pc = effective_caps(b, None, m).provider_micros
    assert led.spent_pool("baseten", pc, model_cfg=m) == 20_000_000 and led.spent_pool("meta", pc, model_cfg=m) == 2_000_000
    c, _ = make_client(tmp, "sweep_meta_medium")
    assert project_total(c, "a", [1]).verdict == "ok"


def test_s4_e_env_cap_applies_to_default_pool_only(world):
    m, b, s, tmp = world
    env = env_m25(DEV_SPEND_CAP_MICRO_USD="1000000")
    mt, _ = make_client(tmp, "meta", env=env)
    p = project_total(mt, "b", calls_for_total(450_000, META, 1))
    assert p.verdict == "budget_exceeded" and "source: env" in p.reason
    sw, _ = make_client(tmp, "sweep_meta_high", env=env)
    q = project_total(sw, "b", [1])
    assert q.verdict == "ok" and q.pool_cap_micros == 75_000_000
    bad, _ = make_client(tmp, "sweep_meta_high", env=env_m25(DEV_SPEND_CAP_MICRO_USD="abc"))
    with pytest.raises(ConfigInvalid):
        project_total(bad, "b", [1])


# ------------------------------------------------------------------ S4 (f) / S19 (k): ledger nyata S1-smoke
def smoke_ledger(runs: Path) -> None:
    for role, cost in (("a", 8_170), ("b", 526_265), ("c", 5_964), ("d", 21_342)):
        syn(runs, role, "meta", CONTRIB, "low", cost)
    syn(runs, "c", "baseten", OPEN, "low", 53_267)
    syn(runs, "b", "baseten", OPEN, "low", 15_460_483)
    for eff, cost in (("medium", 4_637), ("high", 6_745), ("xhigh", 1_156), ("max", 1_887)):
        syn(runs, "c", "baseten", OPEN, eff, cost)
    for eff, cost in (("medium", 151), ("high", 130), ("xhigh", 103)):
        syn(runs, "c", "meta", CONTRIB, eff, cost)


def smoke_numbers(runs: Path, m, b) -> dict:
    led = Ledger(runs)
    pc = effective_caps(b, None, m).provider_micros
    return {"default": led.spent_pool("meta", pc, model_cfg=m), "baseten": led.spent_pool("baseten", pc, model_cfg=m),
            "off_pin": led.spent_off_pin(model_cfg=m), "total_display": led.spent()}


SMOKE_EXPECTED = {"default": 561_741, "baseten": 15_513_750, "off_pin": 14_809, "total_display": 562_125 + 15_528_175}


def test_s4_f_s19_k_real_smoke_ledger_shift(tmp_path):
    m, b, s = cfgs()
    smoke_ledger(tmp_path / "runs")
    assert smoke_numbers(tmp_path / "runs", m, b) == SMOKE_EXPECTED
    assert SMOKE_EXPECTED["total_display"] == 16_090_300
    mt, _ = make_client(tmp_path, "meta")
    p = project_total(mt, "c", [100])
    assert p.pool_spent_micros == 561_741


def test_s8_h1_canary_off_pin_rule_disabled_is_caught(tmp_path, monkeypatch):
    m, b, s = cfgs()
    smoke_ledger(tmp_path / "runs")
    monkeypatch.setattr(budget_mod, "is_off_pin", lambda *a, **k: False)
    got = smoke_numbers(tmp_path / "runs", m, b)
    assert got != SMOKE_EXPECTED and got["default"] == 562_125 and got["baseten"] == 15_528_175 and got["off_pin"] == 0


# ------------------------------------------------------------------ S4 (i): kasus tepi is_off_pin
def _r(**kw):
    base = dict(role="b", provider="meta", model=CONTRIB, quantization=None, effort="medium", kind=None)
    base.update(kw)
    from backend.spark.runrecord import kind_for_role
    base["kind"] = base["kind"] or kind_for_role(base.pop("role"))
    base.pop("role", None)
    return base


def edge_table(fn):
    m, _, _ = cfgs()
    m["profiles"]["twin_low"] = {"provider": "twinprov", "model": "tw"}
    m["profiles"]["twin_high"] = {"provider": "twinprov", "model": "tw", "reasoning_effort": "high"}
    cases = {
        "1": (_r(provider=None), False),
        "2": (_r(effort=None), False),
        "3": (_r(model="model-lain"), False),
        "4": (_r(quantization="Q4"), False),
        "5": (_r(kind="grid"), False),
        "6": (_r(kind="spark_x"), False),
        "7a": (_r(provider="openrouter", model="meta/muse-spark-1.3-contributor", effort="low"), False),
        "7b": (_r(provider="openrouter", model="meta/muse-spark-1.3-contributor", effort="medium"), True),
        "8a": (_r(provider="twinprov", model="tw", effort="medium"), True),
        "8b": (_r(provider="twinprov", model="tw", effort="high"), False),
        "8c": (_r(provider="twinprov", model="tw", effort="low"), False),
        "9a": (_r(role="d", effort="low"), False),
        "9b": (_r(role="d", effort="medium"), True),
        "9c": (_r(provider="lmstudio_local", model=GLIM, quantization="Q4_K_M", effort="high"), False),
        "9d": (_r(provider="lmstudio_local", model=GLIM, quantization="Q4_K_M", effort="medium"), True),
    }
    return m, {k: fn(rec, m) for k, (rec, _) in cases.items()}, {k: v for k, (_, v) in cases.items()}


def test_s4_i_is_off_pin_edge_cases():
    m, got, want = edge_table(is_off_pin)
    assert got == want


def test_s8_h2_canary_literal_not_low_misclassifies_glimmer():
    m, got, want = edge_table(lambda rec, m: rec["effort"] not in (None, "low") and rec["provider"] is not None)
    assert got != want and got["9c"] is True  # Glimmer `high` biaya 0 salah off-pin


# ------------------------------------------------------------------ S19 (l): per pemanggil
def test_s19_l_callers_exclude_off_pin(world):
    m, b, s, tmp = world
    runs = tmp / "runs"
    led = Ledger(runs)
    caps = effective_caps(b, None, m)
    assert pool_limits(led, caps, "meta", "b", model_cfg=m) == (526_265, 1_000_000, 561_741, 2_000_000)
    assert pool_limits(led, caps, "baseten", "b", model_cfg=m) == (15_513_750, 20_000_000, 15_513_750, 20_000_000)
    bt, _ = make_client(tmp, "baseten_open")
    assert project_total(bt, "b", [1]).pool_spent_micros == 15_513_750
    mt, _ = make_client(tmp, "meta")
    p = project_total(mt, "b", [1])
    assert (p.spent_micros, p.spent_role_micros) == (561_741, 526_265)
    # cabang tanpa tabel plafon (`not pc`): semua rekaman on-pin
    nb = dict(b)
    nb.pop("provider_cap_micros")
    nb["version"] = 1
    mt2, _ = make_client(tmp / "n", "meta", budget=nb)
    # ledger sama: salin runs
    import shutil
    shutil.copytree(runs, tmp / "n" / "runs", dirs_exist_ok=True)
    p = project_total(mt2, "b", [1])
    assert (p.spent_micros, p.spent_role_micros) == (16_075_491, 15_986_748)
    # make_gate baseten_open
    gate = cmp.make_gate("baseten", b, m, None, runs)
    assert gate([0], 486_250).ok and not gate([0], 486_251).ok
    assert gate([0], 486_250).spent == 15_513_750
    # tampilan total (system.py) tetap total semua rekaman
    from backend.api.routers.system import ledger_spent_micros
    assert ledger_spent_micros(runs) == 54_080_741


def test_s19_l9_static_scan_every_ledger_caller_passes_model_cfg():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    spent_calls = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        txt = p.read_text(encoding="utf-8")
        offenders += scan_missing_model_cfg(txt, str(p.relative_to(root)))
        if re.search(r"\.spent\(", txt):
            spent_calls.append(p.relative_to(root).as_posix())
    assert offenders == []
    assert set(spent_calls) <= {"api/routers/system.py", "spark/budget.py"}


def scan_missing_model_cfg(text: str, name: str) -> list[str]:
    out = []
    for m_ in re.finditer(r"(?<!def )\b(?:spent_pool|pool_limits|spent_off_pin)\(", text):
        line_start = text.rfind("\n", 0, m_.start()) + 1
        if text[line_start:m_.start()].lstrip().startswith(("def ", "#", '"""')):
            continue
        j, depth = m_.end(), 1
        while depth and j < len(text):
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        if "model_cfg=" not in text[m_.end():j]:
            out.append(f"{name}:{text.count(chr(10), 0, m_.start()) + 1}")
    return out


def test_s8_o_canary_missing_model_cfg_is_detected():
    root = Path(__file__).resolve().parents[1]
    txt = (root / "header_b" / "compare.py").read_text(encoding="utf-8")
    assert scan_missing_model_cfg(txt, "c") == []
    assert scan_missing_model_cfg(txt.replace("spent_pool(provider, pc, model_cfg=model_cfg)", "spent_pool(provider, pc)"), "c")


# ------------------------------------------------------------------ S6
def costs(out_floor, n):
    return cmp.unit_costs(40_000, [300] * n, 300, BT, expected_output_tokens=450, max_output_tokens=1_000,
                          warm_max_output_tokens=1_000, floor=out_floor, warm=True)


@pytest.mark.parametrize("floor,unit,warm", [(8_000, 40_375, 84_375), (12_000, 57_375, 101_375), (16_000, 74_375, 118_375),
                                             (6_000, 31_875, 75_875)])
def test_s6_a_floor_upper_bounds(floor, unit, warm):
    c = costs(floor, 1)
    assert c["unit_upper_cached"] == [unit] and c["warm_upper"] == warm


def test_s6_expected_units_match_s7_h101():
    c = costs(8_000, 1)
    assert c["unit_expected"] == [8_288] and c["warm_expected"] == 52_288


@pytest.mark.parametrize("floor,n,total", [(8_000, 47, 1_982_000), (12_000, 33, 1_994_750), (16_000, 25, 1_977_750)])
def test_s6_b_batch_split(floor, n, total):
    ids = [f"U{i}" for i in range(200)]
    batches = cmp.split_batches(ids, costs(floor, 200), batch_cap=2_000_000, factor_bp=19_312)
    assert len(batches[0]) == n
    c = costs(floor, 200)
    assert sum(c["unit_upper_cached"][:n]) + c["warm_upper"] == total
    assert sum(c["unit_upper_cached"][:n + 1]) + c["warm_upper"] > 2_000_000


def test_s6_e_contributor_sweep_floor_and_low_control():
    me = {"input": 100_000, "cached": 2_000, "output": 200_000}
    c = cmp.unit_costs(40_000, [300] * 2000, 300, me, expected_output_tokens=450, max_output_tokens=1_000,
                       warm_max_output_tokens=1_000, floor=6_000, warm=True)
    assert c["unit_upper_cached"][0] == 1_310 and c["warm_upper"] == 5_230
    ids = [f"U{i}" for i in range(2000)]
    assert len(cmp.split_batches(ids, c, batch_cap=2_000_000, factor_bp=15_700)[0]) == 1_522
    low = cmp.unit_costs(40_000, [300], 300, me, expected_output_tokens=450, max_output_tokens=1_000,
                         warm_max_output_tokens=1_000, floor=None, warm=True)
    assert low["unit_expected"] == [200] and low["warm_expected"] == 4_120


def test_s6_c_cumulative_gate_on_sweep_pool(world):
    m, b, s, tmp = world
    runs = tmp / "runs"
    assert sweep_threshold_micros(b, s) == 75_000_000  # H-105/H-106: sweep.toml nyata cumulative_pct = 100, cap 75M
    gate = cmp.make_gate("baseten", b, m, None, runs, sweep_cfg=s)
    syn(runs, "b", "baseten", OPEN, "xhigh", 35_000_000, rid="fill35m")  # pool sapuan 73.005.250 (batas atas <= batch cap 2.000.000)
    ub = 1_994_750
    v = gate([0], ub)
    assert v.ok and v.spent == 73_005_250 and v.spent + v.batas_atas == 75_000_000
    syn(runs, "b", "baseten", OPEN, "xhigh", 1, rid="plus1")
    v = gate([0], ub)
    assert not v.ok and "cumulative_over_threshold" in v.reasons
    # gerbang utama tidak berubah: [batch_gate].cumulative_pct tetap 80
    assert b["batch_gate"]["cumulative_pct"] == 80
    assert cumulative_threshold_for("baseten", b, effective_caps(b, None, m).provider_micros) == 16_000_000


def test_h105_sweep_pct_missing_falls_back_to_batch_gate_40m(world):
    m, b, s, tmp = world
    s2 = dict(s)
    s2["sweep_pool"] = {k: v for k, v in s["sweep_pool"].items() if k != "cumulative_pct"}
    s2["sweep_pool"]["cap_micros"] = 50_000_000  # config sendiri (sintetis): 50M x 80 // 100
    assert sweep_threshold_micros(b, s2) == 40_000_000


@pytest.mark.parametrize("bad", [0, 101, -1, True, False, 80.0, "100", None])
def test_h105_sweep_pct_invalid_is_config_invalid(world, bad):
    m, b, s, tmp = world
    s2 = dict(s)
    s2["sweep_pool"] = dict(s["sweep_pool"], cumulative_pct=bad)
    with pytest.raises(ConfigInvalid):
        validate_sweep(m, s2)
    with pytest.raises(ConfigInvalid):
        sweep_threshold_micros(b, s2)


def test_s6_d_pools_not_mixed_in_gate(world):
    m, b, s, tmp = world
    runs = tmp / "runs"
    bt = cmp.make_gate("baseten", b, m, None, runs)  # ambang 20.000.000 x 80 // 100 = 16.000.000
    assert bt([0], 486_250).ok and not bt([0], 486_251).ok  # belanja sapuan tidak menggeser gerbang Baseten
    sw = cmp.make_gate("baseten", b, m, None, runs, sweep_cfg=s)
    assert sw([0], 1_994_750).ok and sw([0], 1_994_750).spent == 38_005_250


def test_s6_g_retry_round_judged_on_actual_sweep_spend():
    gcfg = load_gate_config({"batch_gate": {"factor_bp": 15_700, "batch_cap_micros": 2_000_000,
                                            "cumulative_cap_micros": 20_000_000, "cumulative_pct": 80}})
    thr = 40_000_000
    assert evaluate_gate([0], 39_726_500, gcfg, upper_floor=273_500, threshold_micros=thr).ok
    assert not evaluate_gate([0], 39_726_501, gcfg, upper_floor=273_500, threshold_micros=thr).ok
    c = costs(12_000, 3)
    assert sum(c["unit_upper_cached"]) + c["warm_upper"] == 3 * 57_375 + 101_375 == 273_500


# ------------------------------------------------------------------ S9
def rec(role, eff, **kw):
    from .sweep_helpers import syn as _syn  # noqa: F401
    base = {"provider": "meta", "model": CONTRIB, "quantization": None, "effort": eff,
            "kind": "measure" if role == "measure" else ("grid" if role == "grid" else f"spark_{role}")}
    base.update(kw)
    return base


def test_s9_a_no_model_config_is_base_behaviour():
    require_reportable([rec("c", "medium"), rec("b", "low")])  # rekaman sapuan Contributor lolos (keterbatasan P13)
    for prov in ("baseten", "lmstudio_local", "openrouter"):
        with pytest.raises(NotReportable):
            require_reportable([rec("b", "low", provider=prov)])


def test_s9_b_with_model_config_off_pin_meta_rejected():
    m, _, _ = cfgs()
    require_reportable([rec("b", "low")], m)
    for eff in ("medium", "high", "xhigh"):
        with pytest.raises(NotReportable, match="effort"):
            require_reportable([rec("c", eff)], m)  # tiga rekaman S1-smoke Contributor
    for role in ("b", "c", "a"):
        with pytest.raises(NotReportable):
            require_reportable([rec(role, "medium")], m)
    with pytest.raises(NotReportable):
        require_reportable([rec("grid", "medium")], m)  # kind grid: himpunan effort efektif profil
    require_reportable([rec("grid", "low")], m)
    require_reportable([rec("grid", "low", provider="meta")], None)


def test_s9_h_canary_off_pin_check_disabled_lets_smoke_through(monkeypatch):
    m, _, _ = cfgs()
    monkeypatch.setattr("backend.spark.gate.is_off_pin", lambda *a, **k: False)
    require_reportable([rec("c", "medium")], m)  # tanpa pemeriksaan: lolos -> test S19(h) di atas akan gagal
