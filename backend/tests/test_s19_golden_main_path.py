"""M3.2-effort-sweep S19 (+ S8 kenari yang menyangkut inti bersama): jalur utama BYTE-IDENTIK basis bf769cf.

Golden `fixtures/s19_golden.json` diambil dari pohon basis bf769cf SEBELUM kode slice diubah
(`python -m backend.tests.s19_golden`, lihat docstring `s19_golden.py`): body request per peran, RunRecord, kunci cache,
`config_hash`, Projection, pool_limits, ambang kumulatif, gerbang, kunci registri pembatas laju, gerbang laporan.
Setiap butir dijalankan tanpa dan dengan `config/sweep.toml` dibaca: jalur utama tidak membacanya (spy = 0)."""

import json
from pathlib import Path

import pytest

from backend import config as cfgmod
from backend.proposal import gate as proposal_gate
from backend.spark import SparkClient, budget, ratelimit
from backend.spark import sweep as sweepmod
from backend.spark.settings import build_settings
from backend.spark.store import cache_key_for

from . import s19_golden
from .spark_fakes import env_ok

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "s19_golden.json").read_text(encoding="utf-8"))
SHA_INPUT_X = "e1385ec978e3acd13c13b5de14fdc6d385e91f60eaf718e2a211e68ea7b89263"


def canon(x):
    return json.loads(json.dumps(x, sort_keys=True))


@pytest.fixture
def no_sweep_reads(monkeypatch):
    """Spy pembacaan: jalur utama TIDAK boleh membaca config/sweep.toml (ARCHITECTURE §7)."""
    reads: list[str] = []
    real_load = cfgmod.load

    def spy(name, config_dir=None):
        reads.append(name)
        return real_load(name, config_dir)

    monkeypatch.setattr(cfgmod, "load", spy)

    def boom(*a, **k):
        reads.append("sweep")
        raise AssertionError("main path must not read config/sweep.toml")

    monkeypatch.setattr(sweepmod, "load_sweep", boom)
    monkeypatch.setattr("backend.spark.client.load_sweep", boom)
    return reads


def diff_sections(actual: dict) -> set[str]:
    out = set()
    for k in GOLDEN:
        if k == "calls":
            for ck in GOLDEN["calls"]:
                a, g = actual["calls"].get(ck), GOLDEN["calls"][ck]
                for f in ("body", "record", "cache_key", "config_hash"):
                    if canon(a[f]) != canon(g[f]):
                        out.add(f"{ck}:{f}")
        elif canon(actual.get(k)) != canon(GOLDEN[k]):
            out.add(k)
    return out


def test_s19_a_to_j_main_path_equals_base_golden(no_sweep_reads):
    actual = s19_golden.compute()
    assert diff_sections(actual) == set()
    assert canon(actual) == canon(GOLDEN)
    assert "sweep" not in no_sweep_reads  # spy pembacaan config/sweep.toml = 0


def test_s19_a_runrecord_serialization_unchanged():
    from backend.spark.runrecord import RunRecord
    first = next(iter(GOLDEN["calls"].values()))["record"]
    rec = RunRecord.from_dict(first)  # from_dict rekaman lama sah
    # to_json byte-sama dengan golden (kunci terurut, separator tetap; runrecord.py tidak disentuh)
    assert rec.to_json() == json.dumps(first, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert set(rec.to_dict()) == set(first)


def test_s19_config_hash_main_is_golden_two_file_hash():
    m, b = s19_golden.real_configs()
    assert cfgmod.config_hash({"model": dict(m), "budget": dict(b)}) == GOLDEN["config_hash_main"]
    for k, v in GOLDEN["calls"].items():
        assert v["config_hash"] == GOLDEN["config_hash_main"], k


def test_s19_i_cache_key_is_role_independent_and_literal():
    keys = {v["cache_key"] for k, v in GOLDEN["calls"].items() if k.startswith("meta/")}
    assert keys == {"0ccf23a7e2fb969ae86923cf8199c721cbfb0e719d1947a61b7683307ffe5fea"}
    assert set(GOLDEN["calls"]) >= {f"meta/{r}" for r in ("a", "b", "c", "d", "measure")}


def test_s2_b_seven_cache_keys_literals():
    k = lambda prov, model, quant, eff: cache_key_for(prov, model, quant, eff, "P1", "S1", SHA_INPUT_X)  # noqa: E731
    c, o, g = "muse-spark-1.3-contributor", "meta-models/muse-spark-open-1026", "meta/muse-glimmer"
    want = {
        ("meta", c, None, "low"): "0ccf23a7e2fb969ae86923cf8199c721cbfb0e719d1947a61b7683307ffe5fea",
        ("meta", c, None, "medium"): "87b0cce8cc6141e076bac67cee40e1efeddcd4d3d388e49be26854892aacb45e",
        ("meta", c, None, "high"): "086c10b8432da0263cd5fee46afda317987f898a74e9165c7c96b23c28c5424b",
        ("baseten", o, None, "low"): "726d687fa94dee3d25e1923501ed23d588e8bcc86a9e4ef676443e6df8299363",
        ("baseten", o, None, "medium"): "b8a9822aac4134ff15023e92610b98ac2976ccd3e11b5818fa128d08c6301605",
        ("lmstudio_local", g, "Q4_K_M", "high"): "8d23f4330dc3e8dc54eacf005cd4a64ba8a03c9f072ad4e1e9aadf905c339937",
        ("lmstudio_local", g, "Q4_K_M", "medium"): "ded3be45173645fe30c8040793d4877f175f582eb2ceaf11734e8080719304e0",
    }
    for args, h in want.items():
        assert k(*args) == h, args
    assert len(set(want.values())) == 7


def test_s1_d_existing_profiles_settings_unchanged():
    m, _ = s19_golden.real_configs()
    env = {"MUSE_API_KEY": "k" * 12, "MUSE_BASE_URL": "https://x.invalid/v1", "OPENROUTER_API_KEY": "k" * 12,
           "BASETEN_API_KEY": "k" * 12, "BASETEN_BASE_URL": "https://x.invalid/v1"}
    for name in ("meta", "openrouter_dev", "baseten_open"):
        s = build_settings(name, m, env)
        assert s.effort_override is None and s.sweep is False and s.rate_group is None, name
    g = build_settings("glimmer_local", m, env)
    assert g.effort_override == "high" and g.sweep is False and g.rate_group is None


# ---- kenari (S8 g, i, j, l, n): sabotase satu per satu harus menggagalkan pemeriksa golden dengan himpunan TEPAT ----

def test_s8_l_canary_request_body_any_role_leak(monkeypatch):
    for role in ("a", "b", "c", "d", "measure"):
        orig = SparkClient._effort
        monkeypatch.setattr(SparkClient, "_effort", lambda self, r, _role=role, _o=orig: "medium" if r == _role else _o(self, r))
        got = diff_sections(s19_golden.compute())
        monkeypatch.setattr(SparkClient, "_effort", orig)
        assert got and all(f.split(":")[0].endswith("/" + role) for f in got), (role, got)  # hanya peran yang disabotase
        assert f"meta/{role}:body" in got


def test_s8_i_canary_threshold_changes(monkeypatch):
    real = proposal_gate.cumulative_threshold_for
    monkeypatch.setattr(proposal_gate, "cumulative_threshold_for",
                        lambda p, b, c: 15_000_000 if p == "meta" else real(p, b, c))
    monkeypatch.setattr("backend.tests.s19_golden.cumulative_threshold_for", proposal_gate.cumulative_threshold_for)
    assert diff_sections(s19_golden.compute()) >= {"thresholds"}


def test_s8_j_canary_limiter_uses_group_key(monkeypatch):
    real = ratelimit.get_limiter
    monkeypatch.setattr(ratelimit, "get_limiter", lambda p, k, *a, **kw: real("grp", k))
    assert diff_sections(s19_golden.compute()) == {"limiter_keys"}


def test_s8_n_canary_main_reading_sweep_is_detected(no_sweep_reads):
    with pytest.raises(AssertionError):
        sweepmod.load_sweep()
    assert no_sweep_reads == ["sweep"]
    m, b = s19_golden.real_configs()
    # sweep ikut config_hash utama -> hash beda dari golden
    assert cfgmod.config_hash({"model": m, "budget": b, "sweep": {"version": 1}}) != GOLDEN["config_hash_main"]


def test_s19_env_independent_of_sweep_file_presence(tmp_path, monkeypatch):
    """Profil utama dengan config/sweep.toml hilang: jalur utama tidak terpengaruh (S5 (m))."""
    def missing(*a, **k):
        raise sweepmod.SweepConfigMissing("x")
    monkeypatch.setattr("backend.spark.client.load_sweep", missing)
    assert diff_sections(s19_golden.compute()) == set()
    assert env_ok()
