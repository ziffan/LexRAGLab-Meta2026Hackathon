"""M3.2-open-weight-B S7 (fungsi gerbang), S9, S10, S11 (a)-(j), P6/P7/P9/P16 (H-101): plafon provider, pool terpisah,
gerbang per pool. Data sintetis, transport palsu, tanpa Model API. Angka eksak dari docs/scenarios/M3.2-open-weight-B.md."""

import copy

import pytest

from backend.proposal.gate import (
    GateConfig,
    cumulative_threshold_for,
    evaluate_gate,
    load_gate_config,
)
from backend.spark import BudgetExceeded, ConfigInvalid, Ledger, effective_caps, provider_caps
from backend.tests.spark_fakes import Resp, Rig, body_ok, call_args, env_ok, model_cfg, synth

ROLES = {"a": 500_000, "b": 1_000_000, "c": 500_000, "d": 250_000, "measure": 500_000}
GATE = {"factor_bp": 15700, "batch_cap_micros": 2_000_000, "cumulative_cap_micros": 20_000_000, "cumulative_pct": 80}
UNIT = {"input_per_mtok_micros": 1_000_000, "cached_per_mtok_micros": 0, "output_per_mtok_micros": 0}  # 1 micro per token masukan


def bcfg(*, version=2, caps=None, total=2_000_000, **extra):
    c = {"version": version, "dev_total_cap_micros": total, "per_role_cap_micros": dict(ROLES), "batch_gate": dict(GATE)}
    if caps is not None:
        c["provider_cap_micros"] = caps
    c.update(extra)
    return c


def mcfg():
    m = model_cfg()
    m["pricing"]["unit"] = dict(UNIT)
    m["profiles"]["meta_unit"] = {"provider": "meta", "model": "muse-spark-1.3-contributor", "base_url_env": "MUSE_BASE_URL",
                                  "pricing": "unit", "api_key_env": "MUSE_API_KEY", "for_reported_numbers": True}
    m["profiles"]["bt_unit"] = {"provider": "baseten", "model": "meta-models/muse-spark-open-1026", "base_url_env": "MUSE_BASE_URL",
                                "pricing": "unit", "api_key_env": "MUSE_API_KEY", "for_reported_numbers": False}
    m["profiles"]["gl_unit"] = {"provider": "lmstudio_local", "api": "chat_completions", "model": "meta/muse-glimmer",
                                "base_url": "http://127.0.0.1:8080/v1", "quantization": "Q4_K_M", "pricing": "unit",
                                "reasoning_effort": "high", "for_reported_numbers": False}
    return m


def rig(tmp_path, profile, *, budget=None, env=None):
    return Rig(tmp_path, profile=profile, model=mcfg(), budget=budget or bcfg(caps={"baseten": 20_000_000}),
               env=env if env is not None else env_ok(), default=Resp(200, body_ok(usage={"input_tokens": 1, "output_tokens": 1})))


def proj(r, role, micros):
    """Proyeksi satu panggilan tepat `micros` micro-USD (harga uji 1 micro per token masukan)."""
    return r.client.project_batch([call_args(1, role=role, est_input=micros, max_output_tokens=1)])


def f1(runs):
    for role, prov, cost in (("a", "meta", 8_170), ("b", "meta", 526_265), ("c", "meta", 5_964), ("d", "meta", 21_342),
                             ("c", "baseten", 53_267), ("b", "baseten", 5_000_000), ("c", "lmstudio_local", 0)):
        synth(runs, role, prov, cost)


def f2(runs):
    for role, cost in (("b", 900_000), ("a", 400_000), ("c", 400_000), ("d", 200_000), ("measure", 90_000)):
        synth(runs, role, "meta", cost)
    synth(runs, "c", "baseten", 19_000_000)


def da0b0bf(runs):
    for role, prov, cost in (("a", "meta", 8_170), ("b", "meta", 526_265), ("c", "meta", 5_964), ("d", "meta", 21_342),
                             ("a", "baseten", 93_751), ("c", "baseten", 53_267), ("c", "lmstudio_local", 0)):
        synth(runs, role, prov, cost)


# ---------------------------------------------------------------- Ledger.spent_pool

def test_spent_pool_partitions_the_ledger(tmp_path):
    f1(tmp_path)
    led, caps = Ledger(tmp_path), {"baseten": 20_000_000}
    assert led.spent() == 5_615_008
    assert led.spent_pool("baseten", caps, model_cfg=mcfg()) == 5_053_267 and led.spent_pool("baseten", caps, "b", model_cfg=mcfg()) == 5_000_000
    assert led.spent_pool("meta", caps, model_cfg=mcfg()) == 561_741 and led.spent_pool("openrouter", caps, model_cfg=mcfg()) == 561_741  # pool default
    assert led.spent_pool("meta", caps, "b", model_cfg=mcfg()) == 526_265 and led.spent_pool("lmstudio_local", caps, "c", model_cfg=mcfg()) == 5_964
    assert led.spent_pool("meta", {}, model_cfg=mcfg()) == led.spent() == 5_615_008  # tanpa tabel = satu pool
    assert led.spent_pool("baseten", caps, model_cfg=mcfg()) + led.spent_pool("meta", caps, model_cfg=mcfg()) == led.spent()


# ---------------------------------------------------------------- S7 fungsi gerbang (P7)

def test_S7_gate_upper_floor_function():
    cfg = GateConfig(**GATE)
    expected = [8_288] * 100 + [52_288]
    assert sum(expected) == 881_088
    old = evaluate_gate(expected, 0, cfg)
    assert old.batas_atas == 1_383_309 and old.ok and old.reasons == ()
    new = evaluate_gate(expected, 0, cfg, upper_floor=3_263_375)
    assert new.batas_atas == 3_263_375 and not new.ok and new.reasons == ("batas_atas_over_batch_cap",)
    assert new.expected == 881_088
    # floor lebih kecil dari rumus = rumus menang
    assert evaluate_gate(expected, 0, cfg, upper_floor=1_000).batas_atas == 1_383_309
    # kontrol Contributor: upper_floor=0 identik dengan perilaku lama
    ctrl = evaluate_gate([200] * 100 + [4_120], 0, cfg)
    assert ctrl.expected == 24_120 and ctrl.batas_atas == 37_869 and ctrl.ok
    assert evaluate_gate([200] * 100 + [4_120], 0, cfg, upper_floor=0) == ctrl
    for bad in (-1, True, 1.5, "1"):
        with pytest.raises(ValueError):
            evaluate_gate(expected, 0, cfg, upper_floor=bad)


# ---------------------------------------------------------------- S9 gerbang per pool (P9)

def test_S9_threshold_source_and_inclusive_boundary():
    b = bcfg(caps={"baseten": 20_000_000})
    gcfg = load_gate_config(b)
    caps = provider_caps(b)
    assert cumulative_threshold_for("baseten", b, caps) == 16_000_000
    # (a) 14.011.625 + 1.988.375 = 16.000.000 lolos; (b) +1 ditolak
    thr = cumulative_threshold_for("baseten", b, caps)
    a = evaluate_gate([0], 14_011_625, gcfg, upper_floor=1_988_375, threshold_micros=thr)
    assert a.ok and a.batas_atas == 1_988_375
    bad = evaluate_gate([0], 14_011_626, gcfg, upper_floor=1_988_375, threshold_micros=thr)
    assert not bad.ok and bad.reasons == ("cumulative_over_threshold",)
    # (a2) plafon provider 10M: ambang 8M, bukan cumulative_cap_micros (16M)
    b2 = bcfg(caps={"baseten": 10_000_000})
    thr2 = cumulative_threshold_for("baseten", b2, provider_caps(b2))
    assert thr2 == 8_000_000
    assert evaluate_gate([0], 6_011_625, gcfg, upper_floor=1_988_375, threshold_micros=thr2).ok
    r = evaluate_gate([0], 6_011_626, gcfg, upper_floor=1_988_375, threshold_micros=thr2)
    assert r.reasons == ("cumulative_over_threshold",)
    assert evaluate_gate([0], 6_011_626, gcfg, upper_floor=1_988_375).ok  # tanpa ambang pool (16M) salah meloloskan


def test_S9_pool_control_and_contributor_change(tmp_path):
    b = bcfg(caps={"baseten": 20_000_000})
    gcfg, caps = load_gate_config(b), provider_caps(b)
    da0b0bf(tmp_path)
    led = Ledger(tmp_path)
    # (c) gerbang Baseten tidak menambahkan pool default (561.741)
    assert led.spent_pool("baseten", caps, model_cfg=mcfg()) == 147_018
    thr = cumulative_threshold_for("baseten", b, caps)
    assert evaluate_gate([0], 14_011_625, gcfg, upper_floor=1_988_375, threshold_micros=thr).ok
    assert 14_011_625 + 561_741 + 1_988_375 > thr  # jumlah salah akan menolak
    # (d) ronde 2: 171.500
    assert evaluate_gate([0], 15_828_500, gcfg, upper_floor=171_500, threshold_micros=thr).ok
    r = evaluate_gate([0], 15_828_501, gcfg, upper_floor=171_500, threshold_micros=thr)
    assert not r.ok and r.reasons == ("cumulative_over_threshold",)
    # (e) Contributor: ambang cumulative_cap x pct = 16M atas pool default 561.741; tanpa tabel kembali ke total 708.759
    assert cumulative_threshold_for("meta", b, caps) == 16_000_000
    assert led.spent_pool("meta", caps, model_cfg=mcfg()) == 561_741
    assert led.spent_pool("meta", {}, model_cfg=mcfg()) == led.spent() == 708_759
    assert 708_759 - 561_741 == 147_018
    # batas atas Contributor 37.869 pada pool default lolos; selisih 147.018 terukur pada spent yang dipakai
    assert evaluate_gate([200] * 100 + [4_120], 561_741, gcfg, threshold_micros=16_000_000).spent == 561_741


# ---------------------------------------------------------------- S10 penjaga klien (P6)

def test_S10a_baseten_pool_boundary(tmp_path):
    r = rig(tmp_path, "bt_unit")
    f1(r.runs)
    p = proj(r, "b", 14_946_733)
    assert p.verdict == "ok" and p.pool == "baseten" and p.pool_cap_micros == 20_000_000 and p.pool_spent_micros == 5_053_267
    p = proj(r, "b", 14_946_734)
    assert p.verdict == "budget_exceeded"
    for needle in ("baseten", "5053267", "14946734", "20000000"):
        assert needle in p.reason
    with pytest.raises(BudgetExceeded, match="baseten"):
        r.client.run_batch([call_args(1, role="b", est_input=14_946_734, max_output_tokens=1)])
    with pytest.raises(BudgetExceeded, match="baseten"):
        r.client.call(**call_args(1, role="b", est_input=14_946_734, max_output_tokens=1))  # _guard
    assert r.tr.calls == 0


def test_S10b_contributor_role_cap_excludes_baseten(tmp_path):
    r = rig(tmp_path, "meta_unit")
    f1(r.runs)
    p = proj(r, "b", 473_735)
    assert p.verdict == "ok" and p.pool == "default" and p.pool_spent_micros == 561_741 and p.pool_cap_micros == 2_000_000
    assert p.spent_micros == 561_741 and p.spent_role_micros == 526_265
    p = proj(r, "b", 473_736)
    assert p.verdict == "budget_exceeded" and "role b cap" in p.reason and "total cap" not in p.reason
    with pytest.raises(BudgetExceeded, match="role b cap"):
        r.client.call(**call_args(1, role="b", est_input=473_736, max_output_tokens=1))
    assert r.tr.calls == 0


def test_S10c_baseten_spend_does_not_eat_contributor_total(tmp_path):
    r = rig(tmp_path, "meta_unit")
    f2(r.runs)
    assert Ledger(r.runs).spent_pool("meta", {"baseten": 20_000_000}, model_cfg=mcfg()) == 1_990_000
    assert proj(r, "measure", 10_000).verdict == "ok"
    p = proj(r, "measure", 10_001)
    assert p.verdict == "budget_exceeded" and "total cap 2000000" in p.reason and "(source: config)" in p.reason


def test_S10d_default_pool_full_does_not_block_baseten(tmp_path):
    r = rig(tmp_path, "bt_unit")
    f2(r.runs)
    synth(r.runs, "measure", "meta", 10_000)  # pool default penuh: 2.000.000
    assert Ledger(r.runs).spent_pool("meta", {"baseten": 20_000_000}, model_cfg=mcfg()) == 2_000_000
    assert proj(r, "c", 1_000_000).verdict == "ok"
    p = proj(r, "c", 1_000_001)
    assert p.verdict == "budget_exceeded" and "baseten" in p.reason
    # kontrol: peran apa pun tak mengubah pool provider (cap peran tidak berlaku)
    assert proj(r, "d", 1_000_000).verdict == "ok"


def test_S10e_env_lowers_default_pool_only(tmp_path):
    r = rig(tmp_path / "m", "meta_unit", env=env_ok(DEV_SPEND_CAP_MICRO_USD="1000000"))
    f2(r.runs)
    assert effective_caps(r.budget, r.env).total_source == "env"
    p = proj(r, "measure", 1)
    assert p.verdict == "budget_exceeded" and "total cap 1000000" in p.reason and "(source: env)" in p.reason
    b = rig(tmp_path / "b", "bt_unit", env=env_ok(DEV_SPEND_CAP_MICRO_USD="1000000"))
    f2(b.runs)
    pb = proj(b, "c", 1_000_000)
    assert pb.verdict == "ok" and pb.pool_cap_micros == 20_000_000
    assert proj(b, "c", 1_000_001).verdict == "budget_exceeded"
    with pytest.raises(ConfigInvalid):
        effective_caps(b.budget, {"DEV_SPEND_CAP_MICRO_USD": "abc"})


def test_S10f_chat_profile_skips_guard_and_cost_zero_changes_nothing(tmp_path):
    r = rig(tmp_path, "gl_unit")
    f1(r.runs)
    before = Ledger(r.runs).spent_pool("lmstudio_local", {"baseten": 20_000_000}, model_cfg=mcfg())
    r.client._guard("b", 10**12)  # API_CHAT: dilewati, tidak melempar
    synth(r.runs, "c", "lmstudio_local", 0, run_id="syn-extra-zero")
    led = Ledger(r.runs)
    assert led.spent_pool("lmstudio_local", {"baseten": 20_000_000}, model_cfg=mcfg()) == before == 561_741
    assert led.spent_pool("baseten", {"baseten": 20_000_000}, model_cfg=mcfg()) == 5_053_267


def test_S10g_projection_fields(tmp_path):
    r = rig(tmp_path, "meta_unit", budget=bcfg(version=1))  # tanpa tabel = perilaku lama
    synth(r.runs, "c", "meta", 400)
    synth(r.runs, "c", "baseten", 100)
    p = proj(r, "c", 10)
    assert (p.spent_micros, p.spent_role_micros, p.effective_total_cap_micros, p.total_cap_source) == (500, 500, 2_000_000, "config")
    assert (p.role_cap_micros, p.total_micros, p.per_call_micros, p.verdict, p.reason) == (500_000, 10, [10], "ok", None)
    assert p.pool == "default" and p.pool_cap_micros == 2_000_000 and p.pool_spent_micros == 500


# ---------------------------------------------------------------- S11 konfigurasi (P6, P16)

@pytest.mark.parametrize("value", ["20000000", 20000000.0, -1, True, False])
def test_S11_invalid_values(value):
    with pytest.raises(ConfigInvalid, match="baseten"):
        provider_caps(bcfg(caps={"baseten": value}))
    with pytest.raises(ConfigInvalid, match="baseten"):
        effective_caps(bcfg(caps={"baseten": value}), None)


def test_S11e_table_not_a_table():
    for bad in (5, "x", [1], True):
        with pytest.raises(ConfigInvalid, match="provider_cap_micros"):
            provider_caps(bcfg(version=2, **{"provider_cap_micros": bad}))


def test_S11f_unknown_or_empty_provider_key():
    m = model_cfg()
    m["profiles"]["bt"] = {"provider": "baseten", "model": "x", "base_url_env": "A", "api_key_env": "B"}
    assert provider_caps(bcfg(caps={"baseten": 5}), m) == {"baseten": 5}
    with pytest.raises(ConfigInvalid, match="basetn"):
        provider_caps(bcfg(caps={"basetn": 20_000_000}), m)
    with pytest.raises(ConfigInvalid, match="basetn"):
        effective_caps(bcfg(caps={"basetn": 20_000_000}), None, m)
    for k in ("", "  "):
        with pytest.raises(ConfigInvalid):
            provider_caps(bcfg(caps={k: 1}))


def test_S11f_client_rejects_typo_before_network(tmp_path):
    r = rig(tmp_path, "meta_unit", budget=bcfg(caps={"basetn": 20_000_000}))
    with pytest.raises(ConfigInvalid, match="basetn"):
        r.client.project_batch([call_args(1, role="c", est_input=1, max_output_tokens=1)])
    with pytest.raises(ConfigInvalid, match="basetn"):
        r.client.call(**call_args(1, role="c", est_input=1, max_output_tokens=1))
    assert r.tr.calls == 0


def test_S11g_no_table_is_legacy_single_pool(tmp_path):
    b = bcfg(version=1)
    assert provider_caps(b) == {} and effective_caps(b, None).provider_micros == {}
    da0b0bf(tmp_path)
    led = Ledger(tmp_path)
    assert led.spent() == 708_759 and led.spent_pool("baseten", {}, model_cfg=mcfg()) == 708_759 and 2_000_000 - 708_759 == 1_291_241
    remaining = {"a": 398_079, "b": 473_735, "c": 440_769, "d": 228_658}
    for role, rem in remaining.items():
        r = rig(tmp_path / role, "bt_unit", budget=b)
        da0b0bf(r.runs)
        assert proj(r, role, rem).verdict == "ok", role
        p = proj(r, role, rem + 1)
        assert p.verdict == "budget_exceeded" and f"role {role} cap" in p.reason and "total cap" not in p.reason, role
        assert p.pool == "default" and p.spent_micros == 708_759
    r = rig(tmp_path / "x", "bt_unit", budget=b)
    da0b0bf(r.runs)
    for role in remaining:
        assert proj(r, role, 1_291_241).verdict == "budget_exceeded"
    assert proj(r, "measure", 500_000).verdict == "ok"
    f1(r.runs)  # kontrol fixture besar: total 5.615.008 + 708.759 > 2M
    assert all(proj(r, role, 1).verdict == "budget_exceeded" for role in ROLES)


def test_S11h_zero_cap_is_zero_not_unlimited(tmp_path):
    r = rig(tmp_path, "bt_unit", budget=bcfg(caps={"baseten": 0}))
    assert provider_caps(r.budget) == {"baseten": 0}
    assert proj(r, "c", 1).verdict == "budget_exceeded"
    assert r.client.project_batch([call_args(1, role="c", est_input=0, max_output_tokens=1)]).verdict == "ok"


def test_S11i_huge_cap_exact(tmp_path):
    big = 10**15
    r = rig(tmp_path, "bt_unit", budget=bcfg(caps={"baseten": big}))
    synth(r.runs, "c", "baseten", 123)
    assert provider_caps(r.budget) == {"baseten": big}
    assert proj(r, "c", big - 123).verdict == "ok"
    p = proj(r, "c", big - 122)
    assert p.verdict == "budget_exceeded" and str(big) in p.reason
    assert all(isinstance(v, int) for v in (p.pool_cap_micros, p.pool_spent_micros, p.total_micros))


def test_S11j_version_rules():
    assert provider_caps(bcfg(version=2, caps={"baseten": 1})) == {"baseten": 1}
    assert provider_caps(bcfg(version=3, caps={"baseten": 1})) == {"baseten": 1}
    assert provider_caps(bcfg(version=1)) == {}
    for v in (1, None, True, "2"):
        with pytest.raises(ConfigInvalid, match="version"):
            provider_caps(bcfg(version=v, caps={"baseten": 1}))
    c = bcfg(version=2, caps={"baseten": 1})
    del c["version"]
    with pytest.raises(ConfigInvalid, match="version"):
        provider_caps(c)


def test_repo_config_budget_loads_and_is_consistent():
    from backend.spark import load_configs
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    model, budget = load_configs(root / "config")
    assert budget["version"] == 2
    assert provider_caps(budget, model) == {"baseten": 20_000_000}
    assert cumulative_threshold_for("baseten", budget, provider_caps(budget, model)) == 16_000_000
    assert cumulative_threshold_for("meta", budget, provider_caps(budget, model)) == 16_000_000
    assert copy.deepcopy(budget) == budget


# ---------------------------------------------------------------- S9 (e) pemanggil CLI/API + S5 (c) maxLength

def test_pool_limits_contributor_uses_default_pool_and_legacy_without_table(tmp_path):
    from backend.spark import pool_limits, profile_provider
    da0b0bf(tmp_path)
    led = Ledger(tmp_path)
    with_t = effective_caps(bcfg(caps={"baseten": 20_000_000}), None)
    no_t = effective_caps(bcfg(version=1), None)
    assert pool_limits(led, with_t, "meta", "b", model_cfg=mcfg()) == (526_265, 1_000_000, 561_741, 2_000_000)
    assert pool_limits(led, no_t, "meta", "b", model_cfg=mcfg()) == (526_265, 1_000_000, 708_759, 2_000_000)  # tanpa tabel: total ledger
    assert pool_limits(led, with_t, "baseten", "b", model_cfg=mcfg()) == (147_018, 20_000_000, 147_018, 20_000_000)
    m = mcfg()
    assert profile_provider(m, None) == "meta" and profile_provider(m, "bt_unit") == "baseten"
    assert profile_provider({}, None) == ""


def test_header_b_gate_threshold_param():
    from backend.header_b.family import gate
    b = bcfg(caps={"baseten": 20_000_000})
    assert gate(1_000, 14_999_000, b)["cumulative_limit"] == 16_000_000
    g = gate(1_000, 7_999_000, b, threshold=8_000_000)
    assert g["verdict"] == "allow" and g["cumulative_limit"] == 8_000_000
    assert gate(1_001, 7_999_000, b, threshold=8_000_000)["verdict"] == "reject"


def test_compare_a_gate_uses_pool_spend(tmp_path):
    from backend.schema_a.compare_a import _gate
    b = bcfg(caps={"baseten": 20_000_000})
    da0b0bf(tmp_path)
    led = Ledger(tmp_path)
    pc = provider_caps(b)
    assert _gate(b, [100], led.spent_pool("meta", pc, model_cfg=mcfg())).spent == 561_741
    assert _gate(b, [100], led.spent_pool("meta", {}, model_cfg=mcfg())).spent == 708_759
    assert _gate(b, [100], 0, threshold=1).ok is False


def test_S5c_maxlength_enforced_but_strict_check_accepts_it():
    from backend.spark.schema_check import check_strict, validate_instance
    schema = {"type": "object", "additionalProperties": False, "required": ["h"],
              "properties": {"h": {"type": "string", "maxLength": 190}}}
    assert check_strict(schema) is None
    assert validate_instance({"h": "x" * 190}, schema) is None
    assert "maxLength" in validate_instance({"h": "x" * 191}, schema)
