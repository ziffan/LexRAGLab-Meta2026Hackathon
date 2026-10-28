"""M3.2-effort-sweep S1 (profil sapuan), S5 (konfigurasi tidak sah, keterpisahan), P1, P2, P16. Data sintetis, tanpa jaringan."""

import copy

import pytest

from backend import config as cfgmod
from backend.spark import ConfigInvalid, SparkClient
from backend.spark.settings import build_settings
from backend.spark.sweep import (SweepConfigMissing, SweepPoolMissing, load_sweep, merge_sweep, sweep_config_hash,
                                 validate_sweep)

from .m25_fakes import env_m25
from .sweep_helpers import cfgs, make_client

NINE = ["sweep_meta_medium", "sweep_meta_high", "sweep_meta_xhigh", "sweep_baseten_medium", "sweep_baseten_high",
        "sweep_baseten_xhigh", "sweep_glimmer_low", "sweep_glimmer_medium", "sweep_glimmer_xhigh"]


def add(sweep, name, **kw):
    base = {"sweep_of": "meta", "reasoning_effort": "medium", "roles": ["a", "b", "c"]}
    base.update(kw)
    sweep["profiles"][name] = base
    sweep["sweep_pool"]["profiles"].append(name)


def bad(model, sweep, *needles):
    with pytest.raises(ConfigInvalid) as ei:
        validate_sweep(model, sweep)
    for n in needles:
        assert n in str(ei.value), (n, str(ei.value))
    return ei.value


# ------------------------------------------------------------------ S1 (a)
def test_s1_a_nine_profiles_loaded_and_derived_from_parent():
    m, b, s = cfgs()
    assert list(s["profiles"]) == NINE and s["version"] == 1
    allowed = {"sweep_of", "reasoning_effort", "max_output_tokens", "roles", "label", "rate_group"}
    assert all(set(p) <= allowed for p in s["profiles"].values())
    mg = merge_sweep(m, s)
    p = mg["profiles"]["sweep_meta_medium"]
    assert (p["provider"], p["model"], p["pricing"], p["api_key_env"], p["for_reported_numbers"], p["sweep"]) == (
        "meta", "muse-spark-1.3-contributor", "meta", "MUSE_API_KEY", False, True)
    assert (p["reasoning_effort"], p["roles"], p["rate_group"], p["max_output_tokens"]) == ("medium", ["a", "b", "c"], "meta", 6000)
    p = mg["profiles"]["sweep_baseten_xhigh"]
    assert (p["provider"], p["pricing"], p["max_output_tokens"]) == ("baseten", "baseten_open", 16000)
    p = mg["profiles"]["sweep_glimmer_medium"]
    assert (p["provider"], p["api"], p["quantization"], p["base_url"]) == (
        "lmstudio_local", "chat_completions", "Q4_K_M", "http://127.0.0.1:8080/v1")
    assert [mg["profiles"][n]["reasoning_effort"] for n in NINE] == [
        "medium", "high", "xhigh", "medium", "high", "xhigh", "low", "medium", "xhigh"]
    # profil yang ada tidak berubah; config/model asli tidak dimutasi
    for name in ("meta", "openrouter_dev", "baseten_open", "glimmer_local"):
        assert mg["profiles"][name] == m["profiles"][name]
    assert not any(n in m["profiles"] for n in NINE)
    assert m["profiles"]["glimmer_local"]["reasoning_effort"] == "high"


def test_s1_c_controls_pin_wins_over_effort_table():
    m, b, s = cfgs()
    assert m["effort"]["b"] == "low"
    validate_sweep(m, s)  # medium sah walau [effort].b = low; sweep_glimmer_low sah walau glimmer_local pin high


# ------------------------------------------------------------------ S1 (b)
@pytest.mark.parametrize("val", ["max", "none", "", "Medium", 5, True])
def test_s1_b_invalid_effort_values(val):
    m, b, s = cfgs()
    s["profiles"]["sweep_meta_medium"]["reasoning_effort"] = val
    bad(m, s, "sweep_meta_medium", "reasoning_effort")


def test_s1_b_effort_missing_sweep_of_and_roles():
    m, b, s = cfgs()
    del s["profiles"]["sweep_meta_medium"]["reasoning_effort"]
    bad(m, s, "sweep_meta_medium", "reasoning_effort")
    m, b, s = cfgs()
    del s["profiles"]["sweep_meta_medium"]["sweep_of"]
    bad(m, s, "sweep_meta_medium", "sweep_of")
    m, b, s = cfgs()
    s["profiles"]["sweep_meta_medium"]["sweep_of"] = "tidak_ada"
    bad(m, s, "sweep_meta_medium", "sweep_of")
    m, b, s = cfgs()
    s["profiles"]["sweep_meta_medium"]["sweep_of"] = "sweep_meta_high"  # menunjuk profil sweep
    bad(m, s, "sweep_meta_medium", "sweep_of")
    for roles in ([], ["d"], ["a", "x"], "abc"):
        m, b, s = cfgs()
        s["profiles"]["sweep_meta_medium"]["roles"] = roles
        bad(m, s, "sweep_meta_medium", "roles")
    m, b, s = cfgs()
    del s["profiles"]["sweep_meta_medium"]["roles"]  # Q-B12 tetap: tanpa roles ditolak
    bad(m, s, "sweep_meta_medium", "roles")


@pytest.mark.parametrize("key", ["model", "provider", "quantization", "api", "base_url", "base_url_env", "api_key_env",
                                 "pricing", "for_reported_numbers", "sweep", "max_header_tokens", "schema_max_length_chars"])
def test_s1_b_forbidden_identity_keys_even_with_parent_value(key):
    m, b, s = cfgs()
    parent = m["profiles"]["meta"]
    s["profiles"]["sweep_meta_medium"][key] = parent.get(key, "meta_sweep" if key == "provider" else "x")
    bad(m, s, "sweep_meta_medium", key)


def test_s1_b_name_pool_and_tuple_conflicts():
    m, b, s = cfgs()
    s["profiles"]["meta"] = {"sweep_of": "meta", "reasoning_effort": "medium", "roles": ["a"]}  # bentrok config/model
    s["sweep_pool"]["profiles"].append("meta")
    bad(m, s, "meta")
    m, b, s = cfgs()
    s["sweep_pool"]["profiles"].remove("sweep_meta_high")  # profil sweep tak terdaftar
    bad(m, s, "sweep_meta_high")
    m, b, s = cfgs()
    s["sweep_pool"]["profiles"].append("baseten_open")  # non-sweep terdaftar
    bad(m, s, "baseten_open")
    m, b, s = cfgs()
    add(s, "sweep_meta_medium_b", reasoning_effort="medium")  # dua profil bertupel sama
    bad(m, s, "sweep_meta_medium", "sweep_meta_medium_b")
    m, b, s = cfgs()
    m["effort"]["d"] = "medium"  # tupel sapuan = tupel jalur utama peran d
    bad(m, s, "sweep_meta_medium", "[effort].d")
    m, b, s = cfgs()
    add(s, "sweep_meta_x", reasoning_effort="low")
    bad(m, s, "sweep_meta_x")
    m, b, s = cfgs()
    add(s, "sweep_baseten_x", sweep_of="baseten_open", reasoning_effort="low")
    bad(m, s, "sweep_baseten_x", "baseten_open")
    m, b, s = cfgs()
    add(s, "sweep_glimmer_x", sweep_of="glimmer_local", reasoning_effort="high")
    bad(m, s, "sweep_glimmer_x", "glimmer_local")


def test_s5_j_main_path_tuple_conflicts_and_valid_control():
    m, b, s = cfgs()
    m["effort"]["c"] = "high"
    bad(m, s, "sweep_meta_high", "[effort].c")
    m, b, s = cfgs()
    m["effort"]["b"] = "xhigh"  # baseten_open + [effort].b = xhigh vs sweep_baseten_xhigh ([effort] dipakai semua profil Responses)
    del s["profiles"]["sweep_meta_xhigh"]
    s["sweep_pool"]["profiles"].remove("sweep_meta_xhigh")
    bad(m, s, "sweep_baseten_xhigh", "baseten_open", "[effort].b")
    m, b, s = cfgs()
    validate_sweep(m, s)  # dua profil sapuan beda effort sah


# ------------------------------------------------------------------ S5
@pytest.mark.parametrize("cap", ["50000000", 50000000.0, -1, True])
def test_s5_abcd_cap_micros_invalid(cap):
    m, b, s = cfgs()
    s["sweep_pool"]["cap_micros"] = cap
    bad(m, s, "cap_micros")


def test_s5_e_to_h_pool_table_and_version():
    m, b, s = cfgs()
    s["sweep_pool"] = "x"
    bad(m, s, "sweep_pool")
    for v in (None, "1", 2, True, 1.0):
        m, b, s = cfgs()
        if v is None:
            del s["version"]
        else:
            s["version"] = v
        bad(m, s, "version")
    m, b, s = cfgs()
    del s["sweep_pool"]
    with pytest.raises(SweepPoolMissing):
        validate_sweep(m, s)
    for k in ("cap_micros", "profiles"):
        m, b, s = cfgs()
        del s["sweep_pool"][k]
        bad(m, s, k)


def test_s5_i_profiles_list_invalid():
    for val, needle in (("x", "profiles"), ([], "profiles"), ([""], "profiles"), (NINE + ["sweep_meta_high"], "twice"),
                        (NINE + ["typo"], "typo"), (NINE[:-1], NINE[-1])):
        m, b, s = cfgs()
        s["sweep_pool"]["profiles"] = val
        bad(m, s, needle)


def test_s5_k_valid_edges():
    m, b, s = cfgs()
    for cap in (0, 10**15):
        s["sweep_pool"]["cap_micros"] = cap
        validate_sweep(m, s)


def test_s5_l_provider_cap_table_unchanged():
    from backend.spark import provider_caps
    m, bud, s = cfgs()
    assert provider_caps(bud, m) == {"baseten": 20_000_000}
    bud["provider_cap_micros"] = {"basetn": 1}
    with pytest.raises(ConfigInvalid):
        provider_caps(bud, m)


# ------------------------------------------------------------------ S5 (m) (n) (o): keterpisahan dan hash
def test_s5_n_hash_reconstructable_and_differs_from_main(tmp_path):
    m, b, s = cfgs()
    client, _ = make_client(tmp_path, "sweep_meta_medium")
    main, _ = make_client(tmp_path, "meta")
    assert client.config_hash == cfgmod.config_hash({"model": m, "budget": b, "sweep": s})
    assert client.config_hash == sweep_config_hash(m, b, s)
    assert client.config_hash != main.config_hash
    assert main.config_hash == cfgmod.config_hash({"model": m, "budget": b})


def test_s5_n_name_collision_with_config_model_is_invalid():
    m, b, s = cfgs()
    m["profiles"]["sweep_meta_medium"] = copy.deepcopy(m["profiles"]["meta"])
    bad(m, s, "sweep_meta_medium")


def test_s5_m_decision_table(tmp_path, monkeypatch):
    m, b, s = cfgs()
    reads: list[str] = []

    def spy(*a, **k):
        reads.append("sweep")
        return s

    # sel "hilang": profil sweep -> sweep_config_missing; profil non-sweep -> H-101 persis, tak dibaca
    def missing(*a, **k):
        reads.append("sweep")
        raise SweepConfigMissing("sweep_config_missing: x")

    monkeypatch.setattr("backend.spark.client.load_sweep", missing)
    for prof in ("meta", "baseten_open", "glimmer_local"):
        client = SparkClient(prof, model_config=m, budget_config=b, env=env_m25(), runs_dir=tmp_path / prof)
        assert client.config_hash == cfgmod.config_hash({"model": m, "budget": b}) and reads == []
    with pytest.raises(SweepConfigMissing):
        SparkClient("sweep_meta_medium", model_config=m, budget_config=b, env=env_m25(), runs_dir=tmp_path / "x")
    # sel "rusak"
    def broken(*a, **k):
        raise ConfigInvalid("config file is not valid UTF-8 TOML: sweep.toml")

    monkeypatch.setattr("backend.spark.client.load_sweep", broken)
    SparkClient("meta", model_config=m, budget_config=b, env=env_m25(), runs_dir=tmp_path / "y")  # tidak berpengaruh
    with pytest.raises(ConfigInvalid):
        SparkClient("sweep_meta_medium", model_config=m, budget_config=b, env=env_m25(), runs_dir=tmp_path / "z")
    # sel "ada": sweep_config disuntik dibaca; profil non-sweep tidak membacanya
    monkeypatch.setattr("backend.spark.client.load_sweep", spy)
    SparkClient("baseten_open", model_config=m, budget_config=b, env=env_m25(), runs_dir=tmp_path / "w")
    assert reads == ["sweep"]  # hanya dari sel "hilang" di atas (satu), bukan dari profil non-sweep


def test_load_sweep_real_file_and_missing_dir(tmp_path):
    s = load_sweep()
    assert s["version"] == 1 and s["sweep_pool"]["cap_micros"] == 50_000_000
    assert {"sweep_baseten_medium": 19312, "sweep_baseten_high": 19312, "sweep_baseten_xhigh": 19312} == s["factor_bp"]
    with pytest.raises(SweepConfigMissing):
        load_sweep(tmp_path)
    (tmp_path / "sweep.toml").write_text("version = [", encoding="utf-8")
    with pytest.raises(ConfigInvalid):
        load_sweep(tmp_path)


def test_s1_unknown_profile_still_reports_unknown(tmp_path):
    m, b, s = cfgs()
    with pytest.raises(ConfigInvalid, match="unknown profile"):
        SparkClient("nope", model_config=m, budget_config=b, env=env_m25(), runs_dir=tmp_path, sweep_config=s)
    assert build_settings("meta", m, env_m25()).sweep is False
