"""H-104 butir 3: angka biaya header U0 dan README = hasil utama saja (pool default Contributor); belanja eksperimen per pool
terpisah. Data sintetis untuk aturan pool; test README membaca runs/ dan config/ repo (angka hanya dari run tersimpan)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend import config
from backend.api.app import Service, create_app
from backend.spark import Ledger, store
from backend.spark.budget import is_off_pin, pool_spend, provider_caps
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import BASE, K, budget_cfg, model_cfg, synth

REPO = Path(__file__).resolve().parents[2]
CAPS = {"baseten": 20_000_000}
MCFG = model_cfg()


def _seed(runs: Path) -> None:
    synth(runs, "a", "meta", 100, run_id="m-a")
    synth(runs, "b", "meta", None, run_id="m-b-fail", projected=40, status="error")  # upaya gagal: projected ikut buku belanja
    synth(runs, "c", "openrouter", 7, run_id="or-c")
    synth(runs, "c", "lmstudio_local", 0, run_id="gl-c")
    synth(runs, "b", "baseten", 5_000, run_id="bt-b")
    synth(runs, "c", "baseten", None, run_id="bt-c-fail", projected=300, status="error")


def test_pool_spend_matches_ledger_pool_rule(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    led = Ledger(runs)
    got = pool_spend(store.load_records(runs), CAPS)
    assert got == {"default": led.spent_pool("meta", CAPS, model_cfg=MCFG), "baseten": led.spent_pool("baseten", CAPS, model_cfg=MCFG)}
    assert got == {"default": 147, "baseten": 5_300}
    assert sum(got.values()) == led.spent()
    assert list(got) == ["default", "baseten"] and all(type(v) is int for v in got.values())
    # tanpa tabel provider: satu pool = Ledger.spent (perilaku lama)
    assert pool_spend(store.load_records(runs), {}) == {"default": led.spent()}


def test_pool_spend_routes_off_pin_to_sweep_pool(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    synth(runs, "c", "meta", 9_000, run_id="sw-meta-c")
    synth(runs, "b", "baseten", 70_000, run_id="sw-bt-b")
    recs = store.load_records(runs)
    got = pool_spend(recs, CAPS, off_pin=lambda r: r.run_id.startswith("sw-"))
    assert pool_spend(recs, CAPS) == {"default": 9_147, "baseten": 75_300}  # tanpa off_pin: tidak ada kunci sweep
    assert got == {"default": 147, "baseten": 5_300, "sweep": 79_000}
    assert sum(got.values()) == Ledger(runs).spent()
    assert list(got) == ["default", "baseten", "sweep"]


def _client(runs: Path, tmp_path: Path, bcfg: dict) -> TestClient:
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    return TestClient(create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(), budget_config=bcfg))


def test_r1_header_figure_is_default_pool_not_total(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    h = _client(runs, tmp_path, {**budget_cfg(), "version": 2, "provider_cap_micros": dict(CAPS)}).get("/api/health").json()
    led = Ledger(runs)
    assert h["main_results_spent_usd_micros"] == led.spent_pool("meta", CAPS, model_cfg=model_cfg()) == 147
    assert type(h["main_results_spent_usd_micros"]) is int
    assert h["ledger_spent_usd_micros"] == led.spent() == 5_447  # total semua pool tetap ada, bukan angka header
    assert h["pool_spend"] == [{"pool": "default", "spend_usd_micros": 147}, {"pool": "baseten", "spend_usd_micros": 5_300},
                               {"pool": "sweep", "spend_usd_micros": 0}]  # R1 selalu memuat pool sweep (off_pin diteruskan)
    assert sum(p["spend_usd_micros"] for p in h["pool_spend"]) == h["ledger_spent_usd_micros"]


def test_r1_pool_fields_without_provider_table_and_on_bad_config(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    h = _client(runs, tmp_path, budget_cfg()).get("/api/health").json()
    assert h["main_results_spent_usd_micros"] == h["ledger_spent_usd_micros"] == 5_447
    assert h["pool_spend"] == [{"pool": "default", "spend_usd_micros": 5_447}, {"pool": "sweep", "spend_usd_micros": 0}]
    bad = {**budget_cfg(), "version": 1, "provider_cap_micros": dict(CAPS)}  # tabel butuh version >= 2 (H-101 P16)
    h = _client(runs, tmp_path, bad).get("/api/health").json()
    assert h["main_results_spent_usd_micros"] is None and h["pool_spend"] is None
    assert h["ledger_spent_usd_micros"] == 5_447  # bidang lain tetap


def test_r1_pool_fields_null_when_records_unreadable(tmp_path):
    runs = tmp_path / "runs"
    d = runs / "spark" / "records"
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{not json", encoding="utf-8")
    h = _client(runs, tmp_path, budget_cfg()).get("/api/health").json()
    assert h["main_results_spent_usd_micros"] is None and h["pool_spend"] is None


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def test_readme_cost_figures_match_stored_runs():
    """README dan docs/LIMITS.md: angka header = pool default (keduanya); pool Baseten, role A/B/C, sweep di docs/LIMITS.md;
    angka total lama 615,008 tidak dikutip lagi di keduanya."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    text = (REPO / "docs" / "LIMITS.md").read_text(encoding="utf-8")
    caps = provider_caps(config.load("budget"), config.load("model"))
    mcfg = config.load("model")
    pools = pool_spend(store.load_records(REPO / "runs"), caps, off_pin=lambda r: is_off_pin(r, mcfg))  # aturan sama dengan R1
    for name, doc in (("README.md", readme), ("docs/LIMITS.md", text)):
        assert "615,008" not in doc and "615.008" not in doc and "0.615008" not in doc, name
        m = re.search(r"Run cost \(main results\): ([\d,]+) micro-USD \(shown as \$(\d+\.\d{6})\)", doc)
        assert m, f"{name} run cost line (main results) missing"
        assert _num(m.group(1)) == pools["default"], name
        assert m.group(2) == f"{pools['default'] // 1_000_000}.{pools['default'] % 1_000_000:06d}", name
    b = re.search(r"Muse Spark Open comparator pool \(Baseten\): ([\d,]+) micro-USD", text)
    assert b and _num(b.group(1)) == pools["baseten"]
    r = re.search(r"\(role A ([\d,]+), role B ([\d,]+), role C ([\d,]+)\)", text)
    led = Ledger(REPO / "runs")
    assert r and [_num(x) for x in r.groups()] == [led.spent_pool("baseten", caps, role, model_cfg=mcfg) for role in ("a", "b", "c")]
    assert "sweep" in pools
    s = re.search(r"effort sweep pool: ([\d,]+) micro-USD \(Contributor ([\d,]+), Spark Open ([\d,]+), Glimmer ([\d,]+)\)", text)
    assert s, "README effort sweep pool figure missing"
    assert _num(s.group(1)) == pools["sweep"]
    off = [r for r in store.load_records(REPO / "runs") if is_off_pin(r, mcfg)]
    per = [sum(r.spend_micros() for r in off if r.provider == p) for p in ("meta", "baseten", "lmstudio_local")]
    assert [_num(x) for x in s.groups()[1:]] == per and sum(per) == pools["sweep"]


def _number_tokens(doc: str) -> set[str]:
    return {t.rstrip(",.") for t in re.findall(r"\$?\d[\d,\.]*%?", doc)}


def test_readme_id_numbers_match_readme():
    """docs/README.id.md = terjemahan setia: himpunan token angka sama persis dengan README.md (nol pengecualian), dan
    baris biaya utama (padanan Indonesia) memuat angka mikro-USD serta dolar yang sama dengan baris Inggris di README."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    readme_id = (REPO / "docs" / "README.id.md").read_text(encoding="utf-8")
    en, idn = _number_tokens(readme), _number_tokens(readme_id)
    assert en - idn == set(), f"angka README tidak ada di versi ID: {sorted(en - idn)}"
    assert idn - en == set(), f"angka versi ID tidak ada di README: {sorted(idn - en)}"
    m = re.search(r"Run cost \(main results\): ([\d,]+) micro-USD \(shown as (\$\d+\.\d{6})\)", readme)
    assert m, "baris biaya utama README hilang"
    j = re.search(r"Biaya run \(hasil utama\): ([\d,]+) micro-USD \(ditampilkan sebagai (\$\d+\.\d{6})\)", readme_id)
    assert j, "baris biaya utama README.id hilang"
    assert j.groups() == m.groups()
    assert m.group(1) in readme_id and m.group(2) in readme_id


def test_r1_off_pin_record_excluded_from_main_results(tmp_path):
    """Rekaman off-pin (Contributor effort medium, pin profil = low) masuk pool sweep, tidak ke main_results; total tetap memuatnya."""
    from backend.api.routers.system import cost_fields

    runs = tmp_path / "runs"
    _seed(runs)
    mc = model_cfg()
    base = cost_fields(runs, {**budget_cfg(), "version": 2, "provider_cap_micros": dict(CAPS)}, model_cfg=mc)
    plain = pool_spend(store.load_records(runs), CAPS)
    assert {p["pool"]: p["spend_usd_micros"] for p in base["pool_spend"]} == {**plain, "sweep": 0}
    assert base["main_results_spent_usd_micros"] == plain["default"] == 147
    synth(runs, "c", "meta", 4_000, run_id="off-pin-c", model="muse-spark-1.3-contributor", effort="medium")
    synth(runs, "c", "meta", 11, run_id="on-pin-c", model="muse-spark-1.3-contributor", effort="low")
    got = cost_fields(runs, {**budget_cfg(), "version": 2, "provider_cap_micros": dict(CAPS)}, model_cfg=mc)
    pools = {p["pool"]: p["spend_usd_micros"] for p in got["pool_spend"]}
    assert pools["sweep"] == 4_000 and pools["default"] == 158 and got["main_results_spent_usd_micros"] == 158
    assert got["ledger_spent_usd_micros"] == 5_447 + 4_011
