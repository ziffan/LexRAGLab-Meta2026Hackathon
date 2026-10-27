"""M0.1 S26-S31, S40: cost guard (proyeksi, batas inklusif, buku belanja, cap efektif min(config, env))."""

import shutil

import pytest

from backend import config as cfg
from backend.spark import (
    BudgetExceeded,
    ConfigInvalid,
    Ledger,
    effective_caps,
    load_configs,
)
from backend.tests.spark_fakes import (
    Resp,
    Rig,
    body_ok,
    budget_cfg,
    call_args,
    env_ok,
    synth,
)

U400 = {"input_tokens": 3000, "output_tokens": 500}  # 300M + 100M = 400 micro-USD
EST = dict(est_input=3000, max_output_tokens=500)


def rig400(tmp_path, *, role_cap=2000, total=10_000_000, usage=U400, **kw):
    return Rig(tmp_path, budget=budget_cfg(total=total, role=role_cap), default=Resp(200, body_ok(usage=usage)), **kw)


def batch(n, **over):
    return [call_args(i, **EST, **over) for i in range(n)]


def _no_files(runs):
    return not runs.exists() or not [p for p in runs.rglob("*") if p.is_file()]


def test_S26_guard_inclusive_and_pre_call_rejection(tmp_path):
    # (a) batas inklusif: 5 x 400 = 2000
    a = rig400(tmp_path / "a")
    out = a.client.run_batch(batch(5))
    assert a.tr.calls == 5 and out.stopped_reason is None
    assert a.client.project_batch(batch(5)).total_micros == 0  # semua sudah di cache
    # (b) 6 x 400 = 2400 ditolak sebelum panggilan pertama
    b = rig400(tmp_path / "b")
    with pytest.raises(BudgetExceeded) as ei:
        b.client.run_batch(batch(6))
    assert "2400" in str(ei.value) and "2000" in str(ei.value)
    assert b.tr.calls == 0 and _no_files(b.runs)
    # (c) belanja tersimpan 400 + batch 4 = 2000 lolos
    c = rig400(tmp_path / "c")
    synth(c.runs, "c", "meta", 400)
    c.client.run_batch(batch(4))
    assert c.tr.calls == 4
    # (d) tersimpan 401 + 1600 = 2001 ditolak
    d = rig400(tmp_path / "d")
    synth(d.runs, "c", "meta", 401)
    with pytest.raises(BudgetExceeded):
        d.client.run_batch(batch(4))
    assert d.tr.calls == 0


def test_S26_projection_values(tmp_path):
    r = rig400(tmp_path)
    p = r.client.project_batch(batch(5))
    assert p.per_call_micros == [400] * 5 and p.total_micros == 2000 and p.role_cap_micros == 2000
    assert p.verdict == "ok" and p.spent_micros == 0 and p.effective_total_cap_micros == 10_000_000
    assert r.client.project_batch(batch(6)).verdict == "budget_exceeded"
    assert r.tr.calls == 0


def test_S27_projection_is_ceil_per_call(tmp_path):
    est = dict(est_input=1000, max_output_tokens=1)  # 100.2 -> 101 per panggilan
    usage = {"input_tokens": 1000, "output_tokens": 1}
    calls = [call_args(i, **est) for i in range(10)]
    r = rig400(tmp_path / "x", role_cap=1005, usage=usage)
    with pytest.raises(BudgetExceeded):
        r.client.run_batch(calls)
    assert r.tr.calls == 0
    r2 = rig400(tmp_path / "y", role_cap=1010, usage=usage)
    r2.client.run_batch(calls)
    assert r2.tr.calls == 10 and Ledger(r2.runs).spent() == 1010
    assert r2.client.project_batch([call_args(99, **est)]).per_call_micros == [101]


def test_S28_projection_skips_cached_and_duplicates(tmp_path):
    warm = rig400(tmp_path, role_cap=10_000_000)
    warm.client.run_batch(batch(2))  # mengisi cache untuk masukan 0 dan 1
    shutil.rmtree(warm.runs / "spark" / "records")  # belanja kembali 0; cache tetap
    a = Rig(tmp_path, budget=budget_cfg(role=2000), default=Resp(200, body_ok(usage=U400)))
    out = a.client.run_batch(batch(6))
    assert a.tr.calls == 4 and [r.record.status for r in out.results[:2]] == ["cached", "cached"]
    # (b) dua pasang identik -> kunci unik 5
    b = rig400(tmp_path / "b")
    calls = batch(5) + [call_args(0, **EST)]
    assert b.client.project_batch(calls).total_micros == 2000
    out = b.client.run_batch(calls)
    assert b.tr.calls == 5 and out.results[5].record.status == "cached" and out.results[5].record.cost_usd_micros == 0


def test_S29_role_cap_vs_total_cap_across_providers(tmp_path):
    def mk(sub, total, c_cost):
        r = Rig(tmp_path / sub, budget=budget_cfg(total=total, role=2000), default=Resp(200, body_ok(usage=U400)))
        synth(r.runs, "a", "meta", 1500)
        synth(r.runs, "c", "openrouter", c_cost)
        synth(r.runs, "c", "meta", 0, status="cached", run_id="syn-cached")
        return r

    a = mk("a", 3000, 1000)
    pa = a.client.project_batch(batch(2))
    assert pa.verdict == "budget_exceeded" and "total cap" in pa.reason and "role c cap" not in pa.reason
    with pytest.raises(BudgetExceeded, match="total cap"):
        a.client.run_batch(batch(2))
    b = mk("b", 3000, 1000)
    assert b.client.project_batch(batch(1)).verdict == "ok"
    b.client.run_batch(batch(1))
    assert b.tr.calls == 1
    c = mk("c", 100_000_000, 1700)
    pc = c.client.project_batch(batch(1))
    assert pc.verdict == "budget_exceeded" and "role c cap" in pc.reason and "total cap" not in pc.reason
    assert Ledger(c.runs).spent(provider="openrouter") == 1700 and Ledger(c.runs).spent(role="a") == 1500


def test_S29_error_records_with_cost_are_counted(tmp_path):
    r = rig400(tmp_path)
    synth(r.runs, "c", "meta", 120, status="error", run_id="syn-err")
    synth(r.runs, "c", "meta", None, status="error", run_id="syn-unk", projected=400)
    assert Ledger(r.runs).spent() == 520


def test_S30_guard_stops_mid_batch_when_actual_exceeds_projection(tmp_path):
    r = rig400(tmp_path, role_cap=1000, usage={"input_tokens": 3000, "output_tokens": 2000})  # aktual 700
    out = r.client.run_batch(batch(2))
    assert r.tr.calls == 1 and out.stopped_reason == "budget_exceeded" and out.not_run == [1]
    assert out.results[0].record.cost_usd_micros == 700 and out.results[1] is None


@pytest.mark.parametrize("label,mutate,exc", [
    ("a_role_missing", lambda b: b["per_role_cap_micros"].pop("c"), ConfigInvalid),
    ("b_total_missing", lambda b: b.pop("dev_total_cap_micros"), ConfigInvalid),
    ("c_float_cap", lambda b: b.__setitem__("dev_total_cap_micros", 0.5), ConfigInvalid),
    ("c2_float_role_cap", lambda b: b["per_role_cap_micros"].__setitem__("c", 0.5), ConfigInvalid),
    ("c3_negative_cap", lambda b: b.__setitem__("dev_total_cap_micros", -1), ConfigInvalid),
    ("d_role_cap_zero", lambda b: b["per_role_cap_micros"].__setitem__("c", 0), BudgetExceeded),
])
def test_S31_invalid_budget_config_fails_closed(tmp_path, label, mutate, exc):
    b = budget_cfg()
    mutate(b)
    r = Rig(tmp_path, budget=b)
    with pytest.raises(exc):
        r.client.run_batch(batch(1))
    with pytest.raises(exc):
        r.client.call(**call_args(0, **EST))
    assert r.tr.calls == 0


def test_S31e_budget_file_missing(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(cfg.CONFIG_DIR / "model.toml", tmp_path / "config" / "model.toml")
    with pytest.raises(ConfigInvalid):
        load_configs(tmp_path / "config")


# ---- S40: cap efektif = min(config, env) ----

def _rig40(tmp_path, env_cap, **kw):
    env = env_ok()
    if env_cap is not None:
        env["DEV_SPEND_CAP_MICRO_USD"] = env_cap
    return Rig(tmp_path, budget=budget_cfg(total=2_000_000, role=10_000_000), env=env,
               default=Resp(200, body_ok(usage=U400)), **kw)


def test_S40a_env_smaller_wins_inclusive(tmp_path):
    r = _rig40(tmp_path, "1000")
    p2 = r.client.project_batch(batch(2))
    assert p2.verdict == "ok" and p2.effective_total_cap_micros == 1000 and p2.total_cap_source == "env"
    p3 = r.client.project_batch(batch(3))
    assert p3.verdict == "budget_exceeded" and "1000" in p3.reason and "env" in p3.reason
    synth(r.runs, "c", "meta", 200)
    assert r.client.project_batch(batch(2)).verdict == "ok"  # 200 + 800 = 1000
    synth(r.runs, "c", "meta", 1, run_id="syn-extra")
    assert r.client.project_batch(batch(2)).verdict == "budget_exceeded"  # 1001
    assert r.tr.calls == 0


@pytest.mark.parametrize("env_cap", ["4500000", None, "2000000"])
def test_S40bcd_config_cap_applies(tmp_path, env_cap):
    r = _rig40(tmp_path, env_cap)
    ok = r.client.project_batch(batch(5000))
    assert ok.verdict == "ok" and ok.total_micros == 2_000_000 and ok.effective_total_cap_micros == 2_000_000
    over = r.client.project_batch(batch(5001))
    assert over.verdict == "budget_exceeded" and over.total_micros == 2_000_400


@pytest.mark.parametrize("bad", ["-5", "1.5", "abc", "1e3", "+5", "１２"])
def test_S40e_invalid_env_cap_fails_closed(tmp_path, bad):
    r = _rig40(tmp_path, bad)
    with pytest.raises(ConfigInvalid):
        r.client.project_batch(batch(1))
    with pytest.raises(ConfigInvalid):
        r.client.call(**call_args(0, **EST))
    assert r.tr.calls == 0


@pytest.mark.parametrize("empty", ["", "   "])
def test_S40e_empty_env_cap_means_unset(tmp_path, empty):  # O-12 alternatif 2
    r = _rig40(tmp_path, empty)
    p = r.client.project_batch(batch(1))
    assert p.verdict == "ok" and p.effective_total_cap_micros == 2_000_000 and p.total_cap_source == "config"


def test_S40f_zero_cap_blocks_everything(tmp_path):
    r = _rig40(tmp_path, "0")
    assert r.client.project_batch(batch(1)).verdict == "budget_exceeded"
    with pytest.raises(BudgetExceeded):
        r.client.run_batch(batch(1))
    assert r.tr.calls == 0


def test_S40g_env_cap_applies_mid_batch_and_ledger(tmp_path):
    usage = {"input_tokens": 3000, "output_tokens": 2000}  # aktual 700
    r = Rig(tmp_path / "s", budget=budget_cfg(total=2_000_000, role=10_000_000),
            env=env_ok(DEV_SPEND_CAP_MICRO_USD="1000"), default=Resp(200, body_ok(usage=usage)))
    out = r.client.run_batch(batch(2))
    assert r.tr.calls == 1 and out.stopped_reason == "budget_exceeded" and out.not_run == [1]
    assert Ledger(r.runs).spent() == 700
    p = r.client.project_batch([call_args(50, **EST)])
    assert p.verdict == "budget_exceeded" and p.spent_micros == 700 and p.total_micros == 400
    # kontrol: env tidak diset -> panggilan 2 jalan
    k = Rig(tmp_path / "k", budget=budget_cfg(total=2_000_000, role=10_000_000), env=env_ok(),
            default=Resp(200, body_ok(usage=usage)))
    out2 = k.client.run_batch(batch(2))
    assert k.tr.calls == 2 and out2.stopped_reason is None


def test_S40_effective_caps_function():
    b = budget_cfg(total=2_000_000)
    assert effective_caps(b, {"DEV_SPEND_CAP_MICRO_USD": "1000"}).total_micros == 1000
    assert effective_caps(b, {"DEV_SPEND_CAP_MICRO_USD": "9000000"}).total_micros == 2_000_000
    assert effective_caps(b, {}).total_source == "config"
