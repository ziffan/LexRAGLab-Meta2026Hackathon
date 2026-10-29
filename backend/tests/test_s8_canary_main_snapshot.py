"""M3.2-effort-sweep S8 (H-103 S3 bagian C): potret utama + kenari sabotase satu per satu (himpunan item TEPAT) + run sapuan tidak
mengubah potret. Pemeriksa = `s8_potret.potret()` / `diff_items()`. Sintetis, transport palsu, tanpa jaringan."""

import contextlib
import json

import pytest

from backend import config as cfgmod
from backend.api.errors import ApiError
from backend.api.routers import answers as answers_router, system as system_router
from backend.proposal import gate as gate_mod
from backend.spark import SparkClient, ratelimit
from backend.spark import budget as budget_mod
from backend.spark.runrecord import RunRecord
from backend.spark.settings import load_configs
from backend.spark.sweep import load_sweep, merge_sweep

from .s8_potret import K0, PH12, ITEMS, diff_items, potret, put, seed_main, sweep_artifacts
from .sweep_b_helpers import args, run_main, sweep_rig


@pytest.fixture()
def R(tmp_path):
    runs = tmp_path / "runs"
    seed_main(runs)
    return runs


@pytest.fixture()
def base(R):
    return potret(R)


def test_potret_has_all_items_and_main_never_reads_sweep(base):
    assert set(base) == set(ITEMS) and base["main_reads_sweep"] == 0
    assert base["pool_default_spent"] == 561_741 and base["ledger_caller_model_cfg"] == [15_513_750]
    w6 = base["w6_accept_golden"]
    assert (w6["meta"], w6["baseten_open"], w6["sweep_baseten_high"]) == ("meta", "baseten_open", 400)
    assert base["health_model_profiles"] == ["meta", "openrouter_dev", "baseten_open", "glimmer_local"]
    assert list(base["request_body_golden"]) == ["a", "b", "c", "d", "measure"]
    assert base["is_off_pin_table"]["7a"] is False and base["is_off_pin_table"]["7b"] is True and base["is_off_pin_table"]["9c"] is False


def test_potret_is_deterministic(R, base):
    assert diff_items(base, potret(R)) == set()


def test_sweep_runs_leave_main_potret_identical(tmp_path):
    rig, sw = sweep_rig(tmp_path, "sweep_meta_medium")
    R = rig.runs
    seed_main(R)
    before = potret(R)
    for prof in ("sweep_meta_medium", "sweep_baseten_high"):
        extra = ["--confirm-go"] if prof == "sweep_baseten_high" else []
        assert run_main(rig, args(prof, "--max-units", "2", *extra), sweep=sw) == 0
    sweep_artifacts(R)
    assert diff_items(before, potret(R)) == set()


# ---------------------------------------------------------------- sabotase
@contextlib.contextmanager
def patched(obj, name, new):
    old = getattr(obj, name)
    setattr(obj, name, new)
    try:
        yield
    finally:
        setattr(obj, name, old)


def check(R, base, expected, *, override=None):
    after = potret(R, model_override=override) if override else potret(R)
    assert diff_items(base, after) == set(expected)


def test_canary_a_extra_header_file(R, base):
    put(R / "headers" / "pasal" / PH12 / "CH-U9.json", json.dumps({"chunk_id": "CH-U9", "header": "x", "granularity": "pasal", "run_id": "r"}))
    check(R, base, {"uupt_store_hash", "headers_listing"})


def test_canary_b_sweep_answer_written_as_meta(R, base):
    put(R / "answers" / "ans-sweep-1.json", json.dumps({"answer_id": "ans-sweep-1", "item_id": "I1", "slot": "best", "setting_id": "s03",
                                                        "model_profile": "meta"}))
    check(R, base, {"answers_main_listing", "c_2x2_main"})


def test_canary_c_sweep_schema_in_main_dir(R, base):
    put(R / "schemas" / "uupt" / "v3.json", "{}")
    check(R, base, {"schemas_listing"})


def test_canary_d_extra_grid_file(R, base):
    put(R / "grid" / "zz.json", "{}")
    check(R, base, {"grid_listing"})


def test_canary_e_one_byte_of_k0(R, base):
    p = R / "grid" / f"{K0}.json"
    p.write_text(p.read_text(encoding="utf-8").replace("0.25", "0.75"), encoding="utf-8", newline="\n")
    check(R, base, {"grid_listing", "snapshot_r3"})


def test_canary_f_sweep_profiles_merged_into_main_config_health(R, base):
    m, _ = load_configs()
    check(R, base, {"health_model_profiles"}, override=merge_sweep(m, load_sweep()))


def test_canary_g_runrecord_to_dict_extra_key(R, base):
    orig = RunRecord.to_dict
    with patched(RunRecord, "to_dict", lambda self: {**orig(self), "pool": None}):
        check(R, base, {"runrecord_golden"})


def test_canary_h1_off_pin_not_excluded_from_default_pool(R, base):
    orig = budget_mod.Ledger.spent_pool

    def sab(self, provider, caps, role=None, *, model_cfg):
        return orig(self, provider, caps, role, model_cfg={} if provider == "meta" else model_cfg)

    with patched(budget_mod.Ledger, "spent_pool", sab):
        check(R, base, {"pool_default_spent", "projection_golden"})


def test_canary_h2_literal_effort_ne_low_classifier(R, base):
    lit = lambda record, model_cfg, **k: getattr(record, "effort", None) not in (None, "low") if not isinstance(record, dict) else False  # noqa: E731
    with patched(budget_mod, "is_off_pin", lit):
        after = potret(R)
    assert diff_items(base, after) >= {"is_off_pin_table"}
    assert "is_off_pin_table" in diff_items(base, after) and diff_items(base, after) <= {"is_off_pin_table", "pool_default_spent",
                                                                                         "projection_golden", "ledger_caller_model_cfg"}


def test_canary_i_threshold_for_meta_changes(R, base):
    orig = gate_mod.cumulative_threshold_for
    with patched(gate_mod, "cumulative_threshold_for", lambda p, b, c: 20_000_000 if p == "meta" else orig(p, b, c)):
        check(R, base, {"gate_threshold_golden"})


def test_canary_j_limiter_key_uses_group_for_meta(R, base):
    orig = ratelimit.get_limiter
    with patched(ratelimit, "get_limiter", lambda p, k, g=None, m=None: orig(p, k, "grp" if p == "meta" else g, m)):
        check(R, base, {"ratelimit_golden"})


def test_canary_k_w6_rejects_meta_and_baseten(R, base):
    orig = answers_router._profile

    def sab(req, name):
        if name in ("meta", "baseten_open"):
            raise ApiError(422, "validation_failed", "x")
        return orig(req, name)

    with patched(answers_router, "_profile", sab):
        check(R, base, {"w6_accept_golden"})


@pytest.mark.parametrize("role", ["a", "b", "c", "d", "measure"])
def test_canary_l_request_body_of_any_role_changes(R, base, role):
    orig = SparkClient._effort
    with patched(SparkClient, "_effort", lambda self, r: "medium" if r == role else orig(self, r)):
        after = potret(R)
    d = diff_items(base, after)
    assert "request_body_golden" in d
    assert d <= {"request_body_golden", "projection_golden"}  # proyeksi peran b memakai effort yang sama (kunci cache)
    if role != "b":
        assert d == {"request_body_golden"}


def test_canary_m_old_health_row_changes(R, base):
    orig = system_router._profile_row
    with patched(system_router, "_profile_row", lambda req, n, p: {**orig(req, n, p), "effort": "xhigh"} if n == "meta" else orig(req, n, p)):
        check(R, base, {"health_profiles_golden"})


def test_canary_n_main_reads_sweep_and_hash_includes_it(R, base):
    orig = cfgmod.config_hash

    def sab(obj):
        cfgmod.load("sweep")
        return orig({**obj, "sweep": {}})

    with patched(cfgmod, "config_hash", sab):
        check(R, base, {"main_reads_sweep", "config_hash_main_golden"})


def test_canary_o_ledger_caller_drops_model_cfg(R, base):
    orig = budget_mod.Ledger

    class Sab(orig):
        def spent_pool(self, provider, caps, role=None, *, model_cfg):
            return super().spent_pool(provider, caps, role, model_cfg={})

    with patched(budget_mod, "Ledger", Sab):
        check(R, base, {"ledger_caller_model_cfg"})
