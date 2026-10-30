"""M5.1-N1 (`docs/scenarios/M5.1-N1-health-cache.md`): indeks record inkremental R1/R6, pemanasan lifespan, probe lokal latar.
Data sintetis di tmp_path; tanpa jaringan dan tanpa panggilan model."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app as entry
from backend.api.app import Service, create_app
from backend.api.routers import system
from backend.spark import Ledger, local_server, store
from backend.spark.runrecord import RunRecord
from backend.spark.store import DirIndex, canonical_json
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import BASE, K, budget_cfg, model_cfg

CAPS = {"baseten": 20_000_000}
BCFG = {**budget_cfg(), "version": 2, "provider_cap_micros": dict(CAPS)}
COST_KEYS = ("run_cost_usd_micros", "ledger_spent_usd_micros", "main_results_spent_usd_micros", "pool_spend", "run_totals_by_kind")


def _rec(i: int, **over) -> RunRecord:
    kinds = ["spark_a", "spark_b", "spark_c", "spark_d"]
    providers = ["meta", "baseten", "openrouter", "lmstudio_local"]
    base = RunRecord(run_id=f"r{i:03d}", kind=kinds[i % 4], created_at=f"2026-10-{10 + i % 9:02d}T00:00:{i % 60:02d}Z",
                     cache_key="k", corpus_hash=None, config_hash="CFG", clean_sha256=None, loader_rules_version=None,
                     prompt_version=None, prompt_hash=None, model="muse-spark-1.3-contributor",
                     effort="high" if i % 7 == 0 else "low", tokenizer=None, embedder=None, packing=None,
                     usage_input_tokens=None if i % 5 == 0 else 100 + i, usage_cached_tokens=i,
                     usage_output_tokens=None if i % 6 == 0 else 10 + i,
                     cost_usd_micros=None if i % 4 == 0 else 1_000 + 37 * i,
                     projected_cost_usd_micros=50 if i % 4 == 0 else None, latency_ms=0, host="authoritative",
                     device="remote", provider=providers[i % 4], quantization=None,
                     status="error" if i % 4 == 0 else "ok", error=None)
    return dataclasses.replace(base, **over)


def _grid_env(runs: Path, name: str, body: bytes) -> Path:
    d = runs / "grid"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(body)
    return p


def _seed(runs: Path, n: int = 30) -> None:
    for i in range(n):
        store.save_record(runs, _rec(i))
    g = _rec(99, kind="grid", provider=None, effort=None, cost_usd_micros=None, projected_cost_usd_micros=None, status="ok")
    _grid_env(runs, "g1.json", json.dumps({"record": g.to_dict()}).encode())
    _grid_env(runs, "g2.json", json.dumps({"record": None}).encode())  # belum selesai: dilewati
    _grid_env(runs, "g3.json", b"{broken")  # rusak: dilewati
    (runs / "spark" / "records" / "r999.json.tmp").write_text("{tmp", encoding="utf-8")  # tulis atomik setengah jalan


def _old(runs: Path) -> dict:
    return system.cost_fields(runs, BCFG, model_cfg=model_cfg())


def _new(runs: Path, idx: system.RunIndex) -> dict:
    return system.cost_fields(runs, BCFG, model_cfg=model_cfg(), index=idx)


def _assert_same(runs: Path, idx: system.RunIndex) -> dict:
    old, new = _old(runs), _new(runs, idx)
    assert canonical_json(new).encode() == canonical_json(old).encode()
    assert set(COST_KEYS) <= set(new)
    if new["ledger_spent_usd_micros"] is not None:
        assert new["ledger_spent_usd_micros"] == Ledger(runs).spent()
    assert [r.to_dict() for r in system.all_records(runs, idx)] == [r.to_dict() for r in system.all_records(runs)]
    return new


def _client(runs: Path, tmp_path: Path, **kw) -> TestClient:
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    return TestClient(create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(),
                                 budget_config=BCFG, **kw))


def _r6_expected(runs: Path, n: int = 500) -> list[dict]:
    recs = system.all_records(runs)
    recs.sort(key=lambda r: (r.created_at, r.run_id), reverse=True)
    return [r.to_dict() for r in recs[:n]]


# T1 identitas byte
def test_t1_indexed_fields_and_r6_identical_to_unindexed(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    idx = system.RunIndex(runs)
    f = _assert_same(runs, idx)
    assert f["main_results_spent_usd_micros"] is not None and f["pool_spend"][-1]["pool"] == "sweep"
    assert any(p["spend_usd_micros"] > 0 for p in f["pool_spend"] if p["pool"] == "sweep")  # off-pin ikut terwakili
    assert _assert_same(runs, idx) == f  # panggilan kedua (dari cache) tetap sama
    c = _client(runs, tmp_path)
    h = c.get("/api/health").json()
    assert canonical_json({k: h[k] for k in COST_KEYS}) == canonical_json({k: _old(runs)[k] for k in COST_KEYS})
    assert canonical_json(c.get("/api/runs?limit=500").json()) == canonical_json(_r6_expected(runs))
    assert canonical_json(c.get("/api/runs?kind=spark_b&limit=3").json()) == canonical_json(
        [r for r in _r6_expected(runs) if r["kind"] == "spark_b"][:3])


# T2 tidak basi setelah record baru
def test_t2_new_record_reflected_on_next_call(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    c = _client(runs, tmp_path)
    before = c.get("/api/health").json()
    c.get("/api/runs?limit=500")
    store.save_record(runs, _rec(201, run_id="new1", provider="meta", kind="spark_c", cost_usd_micros=1_234,
                                 projected_cost_usd_micros=None, status="ok", effort="low",
                                 created_at="2026-10-30T23:59:59Z"))
    after = c.get("/api/health").json()
    assert after["main_results_spent_usd_micros"] == before["main_results_spent_usd_micros"] + 1_234
    assert after["ledger_spent_usd_micros"] == Ledger(runs).spent()
    assert c.get("/api/runs?limit=1").json()[0]["run_id"] == "new1"


# T3 hapus dan tulis ulang
def test_t3_delete_and_rewrite_reflected(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    idx = system.RunIndex(runs)
    _assert_same(runs, idx)
    recdir = runs / "spark" / "records"
    (recdir / "r001.json").unlink()
    _assert_same(runs, idx)
    # (a) ukuran berubah
    store.save_record(runs, _rec(2, cost_usd_micros=999_999))
    assert _assert_same(runs, idx)["run_cost_usd_micros"] == _old(runs)["run_cost_usd_micros"]
    # (b) ukuran sama, mtime berbeda (biaya 1111 -> 2222)
    p = recdir / "r003.json"
    st = p.stat()
    rec = _rec(3, cost_usd_micros=1111)
    store.save_record(runs, rec)
    size1 = p.stat().st_size
    v1 = _assert_same(runs, idx)["run_cost_usd_micros"]
    store.save_record(runs, dataclasses.replace(rec, cost_usd_micros=2222))
    assert p.stat().st_size == size1
    os.utime(p, ns=(st.st_atime_ns, p.stat().st_mtime_ns + 1_000_000_000))
    assert _assert_same(runs, idx)["run_cost_usd_micros"] == v1 + 1111


# T4 galat dan pulih
def test_t4_corrupt_record_then_fixed(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    c = _client(runs, tmp_path)
    ok = c.get("/api/health").json()
    bad = runs / "spark" / "records" / "zz-bad.json"
    bad.write_text("{not json", encoding="utf-8")
    h = c.get("/api/health").json()
    assert all(h[k] is None for k in COST_KEYS)
    assert c.get("/api/runs").status_code == 500
    assert c.get("/api/health").json()["run_cost_usd_micros"] is None  # tetap gagal (tidak di-cache sebagai sah)
    bad.unlink()
    assert {k: c.get("/api/health").json()[k] for k in COST_KEYS} == {k: ok[k] for k in COST_KEYS}
    assert c.get("/api/runs").status_code == 200


def test_t4_grid_envelopes_follow_changes_and_transient_read_errors(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    _seed(runs)
    idx = system.RunIndex(runs)
    _assert_same(runs, idx)
    g = _rec(98, run_id="grid2", kind="grid", provider=None, effort=None, cost_usd_micros=None,
             projected_cost_usd_micros=None, status="ok")
    p3 = _grid_env(runs, "g3.json", json.dumps({"record": g.to_dict()}).encode())  # rusak -> sah
    _grid_env(runs, "g2.json", json.dumps({"record": dataclasses.replace(g, run_id="grid3").to_dict()}).encode())
    ids = {r.run_id for r in idx.grid.load()}
    assert {"grid2", "grid3"} <= ids
    _assert_same(runs, idx)
    # PermissionError sesaat saat baca: dilewati panggilan ini (seperti jalur lama), tidak di-cache
    os.utime(p3, ns=(p3.stat().st_atime_ns, p3.stat().st_mtime_ns + 1_000_000_000))
    real = pathlib.Path.read_bytes
    calls = {"n": 0}

    def flaky(self):
        if self.name == "g3.json" and calls["n"] == 0:
            calls["n"] += 1
            raise PermissionError("locked")
        return real(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", flaky)
    assert "grid2" not in {r.run_id for r in idx.grid.load()}
    assert "grid2" in {r.run_id for r in idx.grid.load()}  # pulih tanpa perubahan stat


# T5 tanpa parse ulang
def test_t5_unchanged_directory_parses_nothing(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    n = {"c": 0}

    def parse(p):
        n["c"] += 1
        return store._parse_record(p)

    idx = DirIndex(runs / "spark" / "records", parse)
    first = idx.load()
    assert n["c"] == 30 and len(first) == 30
    assert [r.to_dict() for r in idx.load()] == [r.to_dict() for r in first]
    assert n["c"] == 30
    store.save_record(runs, _rec(250))
    idx.load()
    assert n["c"] == 31


# T6 serentak: satu pemindaian; galat melepas lock
def test_t6_concurrent_cold_load_parses_once(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    gate, started = threading.Event(), threading.Event()
    n = {"c": 0}
    lk = threading.Lock()

    def parse(p):
        with lk:
            n["c"] += 1
        started.set()
        gate.wait(5)
        return store._parse_record(p)

    idx = DirIndex(runs / "spark" / "records", parse)
    bar = threading.Barrier(4)
    out: list = []

    def go():
        bar.wait()
        out.append([r.run_id for r in idx.load()])

    ths = [threading.Thread(target=go) for _ in range(4)]
    for t in ths:
        t.start()
    assert started.wait(5)
    time.sleep(0.2)  # tiga thread lain sampai di lock
    gate.set()
    for t in ths:
        t.join(10)
    assert n["c"] == 30 and len(out) == 4 and all(o == out[0] for o in out)


def test_t6_parse_error_releases_lock(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    state = {"fail": True}

    def parse(p):
        if state["fail"]:
            raise ValueError("boom")
        return store._parse_record(p)

    idx = DirIndex(runs / "spark" / "records", parse)
    with pytest.raises(ValueError):
        idx.load()
    state["fail"] = False
    done: list = []
    t = threading.Thread(target=lambda: done.append(len(idx.load())))
    t.start()
    t.join(5)
    assert done == [30]


# T7 lifespan pemanasan; default tanpa pemanasan
def _wait_warm(idx: system.RunIndex, n: int) -> None:
    deadline = time.monotonic() + 10
    while len(idx.records._entries) < n and time.monotonic() < deadline:
        time.sleep(0.02)


def test_t7_lifespan_warms_index_before_first_request(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    app = create_app(svc, env={}, model_config=model_cfg(), budget_config=BCFG, warm_index=True)
    with TestClient(app) as c:
        idx = system.run_index(app.state, runs)
        _wait_warm(idx, 30)
        assert len(idx.records._entries) == 30 and len(idx.grid._entries) == 3
        n = {"c": 0}
        real = idx.records._parse

        def spy(p):
            n["c"] += 1
            return real(p)

        idx.records._parse = spy
        h = c.get("/api/health").json()
        assert n["c"] == 0
        assert h["ledger_spent_usd_micros"] == Ledger(runs).spent()


def test_t7_default_app_does_not_warm(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    app = create_app(svc, env={}, model_config=model_cfg(), budget_config=BCFG)
    with TestClient(app):
        time.sleep(0.2)
        assert getattr(app.state, "run_indexes", None) is None


def test_t7b_server_factory_warms(monkeypatch):
    seen = {}
    monkeypatch.setattr(entry, "create_app", lambda **kw: seen.update(kw) or "app")
    assert entry.server_app() == "app" and seen == {"warm_index": True}


# T9 mutasi hasil tidak bocor
def test_t9_mutating_result_list_does_not_leak(tmp_path):
    runs = tmp_path / "runs"
    _seed(runs)
    idx = system.RunIndex(runs)
    a = system.all_records(runs, idx)
    ids = [r.run_id for r in a]
    a.sort(key=lambda r: r.run_id, reverse=True)
    a.append(_rec(400))
    b = idx.records.load()
    b.clear()
    assert [r.run_id for r in system.all_records(runs, idx)] == ids


# Probe server lokal: single-flight dan pembaruan latar
def test_probe_cached_single_flight(monkeypatch):
    monkeypatch.setattr(local_server, "_cache", {})
    n = {"c": 0}

    def slow(base_url, model, **kw):
        n["c"] += 1
        time.sleep(0.3)
        return False, "down"

    monkeypatch.setattr(local_server, "probe_models", slow)
    bar = threading.Barrier(4)
    out: list = []

    def go():
        bar.wait()
        out.append(local_server.probe_cached("http://127.0.0.1:9/v1", "m"))

    ths = [threading.Thread(target=go) for _ in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(5)
    assert n["c"] == 1 and out == [(False, "down")] * 4


def test_refresh_loop_keeps_cache_fresh_so_health_never_probes(monkeypatch):
    monkeypatch.setattr(local_server, "_cache", {})
    stop = threading.Event()
    calls = {"c": 0}

    def fake(base_url, model):
        calls["c"] += 1
        return True, "Available."

    t = threading.Thread(target=local_server.refresh_loop, args=([("http://127.0.0.1:9/v1", "m")], stop),
                         kwargs={"interval": 0.05, "probe": fake}, daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while calls["c"] < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    monkeypatch.setattr(local_server, "probe_models", lambda *a, **k: pytest.fail("health must not probe"))
    assert local_server.probe_cached("http://127.0.0.1:9/v1", "m") == (True, "Available.")
    stop.set()
    t.join(5)
    assert not t.is_alive() and calls["c"] >= 3


def test_lifespan_probe_refresh_only_outside_replay(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    _seed(runs, 2)
    started: list = []
    monkeypatch.setattr(local_server, "refresh_loop", lambda targets, stop, **kw: started.append(targets))
    m = model_cfg()
    m["profiles"]["gl"] = {"provider": "lmstudio_local", "api": "chat_completions", "model": "meta/muse-glimmer",
                           "base_url": "http://127.0.0.1:9/v1"}
    m["profiles"]["gl2"] = {**m["profiles"]["gl"], "base_url": "http://127.0.0.1:10/v1"}
    both = [[("http://127.0.0.1:9/v1", "meta/muse-glimmer")], [("http://127.0.0.1:10/v1", "meta/muse-glimmer")]]
    for replay, expect in ((True, []), (False, both)):  # satu thread per target (siklus tidak bertambah per profil)
        started.clear()
        svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
        app = create_app(svc, env={}, model_config=m, budget_config=BCFG, replay=replay, warm_index=True)
        with TestClient(app):
            deadline = time.monotonic() + 2
            while len(started) < len(expect) and time.monotonic() < deadline:
                time.sleep(0.01)
        assert sorted(started) == sorted(expect)
