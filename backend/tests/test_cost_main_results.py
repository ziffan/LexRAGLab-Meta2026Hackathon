"""H-104 butir 3: angka biaya header U0 dan README = hasil utama saja (pool default Contributor); belanja eksperimen per pool
terpisah. Data sintetis untuk aturan pool; test README membaca runs/ dan config/ repo (angka hanya dari run tersimpan)."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend import config
from backend.api.app import Service, create_app
from backend.spark import Ledger, store
from backend.spark.budget import pool_spend, provider_caps
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import BASE, K, budget_cfg, model_cfg, synth

REPO = Path(__file__).resolve().parents[2]
CAPS = {"baseten": 20_000_000}


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
    assert got == {"default": led.spent_pool("meta", CAPS), "baseten": led.spent_pool("baseten", CAPS)}
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
    assert h["main_results_spent_usd_micros"] == led.spent_pool("meta", CAPS) == 147
    assert type(h["main_results_spent_usd_micros"]) is int
    assert h["ledger_spent_usd_micros"] == led.spent() == 5_447  # total semua pool tetap ada, bukan angka header
    assert h["pool_spend"] == [{"pool": "default", "spend_usd_micros": 147}, {"pool": "baseten", "spend_usd_micros": 5_300}]
    assert sum(p["spend_usd_micros"] for p in h["pool_spend"]) == h["ledger_spent_usd_micros"]


def test_r1_pool_fields_without_provider_table_and_on_bad_config(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    h = _client(runs, tmp_path, budget_cfg()).get("/api/health").json()
    assert h["main_results_spent_usd_micros"] == h["ledger_spent_usd_micros"] == 5_447
    assert h["pool_spend"] == [{"pool": "default", "spend_usd_micros": 5_447}]
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
    """README: angka header = pool default; pool Baseten terpisah; angka total lama 615,008 tidak dikutip lagi."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "615,008" not in text and "615.008" not in text and "0.615008" not in text
    caps = provider_caps(config.load("budget"), config.load("model"))
    pools = pool_spend(store.load_records(REPO / "runs"), caps)
    m = re.search(r"Run cost \(main results\): ([\d,]+) micro-USD \(shown as \$(\d+\.\d{6})\)", text)
    assert m, "README run cost line (main results) missing"
    assert _num(m.group(1)) == pools["default"]
    assert m.group(2) == f"{pools['default'] // 1_000_000}.{pools['default'] % 1_000_000:06d}"
    b = re.search(r"Muse Spark Open comparator pool \(Baseten\): ([\d,]+) micro-USD", text)
    assert b and _num(b.group(1)) == pools["baseten"]
    r = re.search(r"\(role A ([\d,]+), role B ([\d,]+), role C ([\d,]+)\)", text)
    led = Ledger(REPO / "runs")
    assert r and [_num(x) for x in r.groups()] == [led.spent_pool("baseten", caps, role) for role in ("a", "b", "c")]
    assert "sweep" not in pools  # main: pool sapuan belum dirangkai; README menyatakan belum ada run tersimpan
