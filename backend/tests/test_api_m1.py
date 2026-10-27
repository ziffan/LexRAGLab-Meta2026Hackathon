"""API terpadu (INT-a): R1, R3, R4, R5, R6, W1 lewat satu `create_app`, galat seragam. Korpus nyata, encoder palsu, runs di tmp."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import Service, create_app
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import BASE, K, budget_cfg, model_cfg

FAM = "/api/families/uupt"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("m1api")
    enc = FakeEncoder()
    svc = Service(tokenizer=get_tokenizer(), runs_dir=root / "runs", encoder=enc, embed_cache_dir=root / "emb")
    app = create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(), budget_config=budget_cfg())
    return {"svc": svc, "app": app, "client": TestClient(app, raise_server_exceptions=False), "enc": enc, "root": root}


@pytest.fixture(scope="module")
def client(world):
    return world["client"]


def sid(world, chunker, mode, budget=2000, header=False):
    return next(s["setting_id"] for s in world["svc"].settings("uupt") if s["chunker"] == chunker and s["retrieval_mode"] == mode
                and s["budget_tokens"] == budget and s["header_b"] is header)


def clean_error(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"} and body["error"]["code"] == code
    low = r.text.lower()
    assert "traceback" not in low and K not in r.text and BASE not in r.text and "\\" not in r.text
    return body


# ---- satu app, galat seragam (R1/R6 dan route M1 memakai handler yang sama) ----
def test_r1_health_is_on_the_unified_app_without_leaking(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert K not in r.text and BASE not in r.text


def test_r1_run_cost_is_exact_sum_beyond_r6_max_limit(tmp_path):
    from backend.api.routers.system import MAX_LIMIT

    from .spark_fakes import synth

    runs = tmp_path / "runs"
    n = MAX_LIMIT + 7
    for i in range(n):
        synth(runs, "a", "meta", None if i % 10 == 0 else 3 + i, run_id=f"cost-{i:04d}")
    want = sum(3 + i for i in range(n) if i % 10 != 0)
    svc = Service(tokenizer=get_tokenizer(), runs_dir=runs, encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    c = TestClient(create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(), budget_config=budget_cfg()))
    r = c.get("/api/health")
    assert r.status_code == 200
    got = r.json()["run_cost_usd_micros"]
    assert type(got) is int and got == want
    assert len(c.get("/api/runs", params={"limit": str(MAX_LIMIT)}).json()) == MAX_LIMIT  # R6 terpotong; R1 tidak
    assert K not in r.text and BASE not in r.text


def test_r1_run_cost_zero_without_records_and_null_when_unreadable(tmp_path):
    svc = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs", encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    c = TestClient(create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(), budget_config=budget_cfg()))
    assert c.get("/api/health").json()["run_cost_usd_micros"] == 0
    d = tmp_path / "runs" / "spark" / "records"
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{not json", encoding="utf-8")
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["run_cost_usd_micros"] is None


def test_uniform_error_shape_across_modules(client, world):
    clean_error(client.get("/api/runs", params={"kind": "bogus"}), 400, "invalid_request")
    clean_error(client.get("/api/does-not-exist"), 404, "not_found")
    clean_error(client.get("/api/families/xyz/snapshot"), 400, "invalid_request")
    clean_error(client.get(f"{FAM}/retrieval"), 400, "invalid_request")  # parameter wajib hilang
    clean_error(client.get(f"{FAM}/snapshot", params={"budget_tokens": "abc"}), 400, "invalid_request")
    clean_error(client.post(f"{FAM}/grid/run", json={"budget_tokens": "abc"}), 400, "invalid_request")
    clean_error(client.put("/api/health"), 405, "invalid_request")


def test_unexpected_exception_is_500_without_trace(world, monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("secret internal detail C:\\path\\x.py")

    monkeypatch.setattr(Service, "run_grid", boom)
    r = TestClient(world["app"], raise_server_exceptions=False).post(f"{FAM}/grid/run", json={})
    clean_error(r, 500, "internal_error")
    assert "secret" not in r.text


def test_server_binds_localhost_only():
    import backend.api.__main__ as m
    assert m.HOST == "127.0.0.1"


# ---- sebelum run: grid null (R3 tidak pernah menjalankan grid) ----
def test_r3_before_any_run_has_null_grid_and_split(client, world):
    d = client.get(f"{FAM}/snapshot").json()
    assert d["grid"] is None and d["metrics"] == [] and d["quality"] == [] and d["split"] is None
    assert "report" in d and d["report"] is None  # H-077: tanpa grid, laporan null
    assert len(d["settings"]) == 36 and not (world["root"] / "runs").exists()  # tidak menulis apa pun
    assert world["enc"].encode_calls == 0


# ---- W1 ----
def test_w1_runs_grid_then_cached(client, world):
    r1 = client.post(f"{FAM}/grid/run", json={"budget_tokens": None})
    assert r1.status_code == 200, r1.text
    rec = r1.json()
    assert rec["kind"] == "grid" and rec["status"] == "ok" and rec["cost_usd_micros"] == 0 and rec["packing"] == "stop"
    assert rec["tokenizer"]["name"] == get_tokenizer().info.name and rec["embedder"]["name"] == "fake-enc"
    calls = world["enc"].encode_calls
    assert calls > 0
    r2 = client.post(f"{FAM}/grid/run", json={"budget_tokens": 1000})
    assert r2.status_code == 200 and r2.json()["status"] == "cached" and r2.json()["cache_key"] == rec["cache_key"]
    assert world["enc"].encode_calls == calls  # nol hitung
    assert (world["root"] / "runs" / "grid" / f"{rec['cache_key']}.json").is_file()
    clean_error(client.post(f"{FAM}/grid/run", json={"budget_tokens": 1234}), 400, "invalid_request")
    clean_error(client.post("/api/families/akta/grid/run", json={}), 422, "validation_failed")


# ---- R3 sesudah run ----
# Asal angka (data/butir/uupt.v12.jsonl, 20 butir; runs_dir sementara kosong -> split v1 dibuat dari nol, bukan perluasan; rasio 0.4 config/grid):
# strata (origin, mode): operator-literal 4, operator-parafrase 5, spark-literal 4, spark-parafrase 7.
# held_out = round(0.4*n): 2 + 2 + 2 + 3 = 9; tune = 20 - 9 = 11; kontrol di held_out = 2 + 2 = 4 (>= 3, tanpa pemindahan).
S_V12_BY_SPLIT = {"tune": 11, "held_out": 9}


def test_r3_after_run_has_split_grid_frontier_selected_quality(client, world):
    d = client.get(f"{FAM}/snapshot").json()
    assert d["split"]["split_version"] == 1 and d["items_summary"]["by_split"] == S_V12_BY_SPLIT
    assert d["items_summary"]["control_in_held_out"] >= 3 and {i["split"] for i in d["items"]} == {"tune", "held_out"}
    g = d["grid"]
    assert set(g["tune"]) == {"points", "frontier"} and set(g["held_out"]) == {"points", "frontier"}
    assert g["tune"]["frontier"]["split"] == "tune" and g["tune"]["frontier"]["budget_tokens"] == 2000
    assert len(g["tune"]["points"]) == 6 and len(g["held_out"]["points"]) == 6
    assert g["selected"]["tune_point"]["split"] == "tune" and g["selected"]["budget_tokens"] == 2000
    assert len(g["skipped"]) == 12 and all(s["reason"] for s in g["skipped"])
    assert g["quality_comparison"]["selected_setting_id"] == g["selected"]["setting_id"]
    assert len(d["metrics"]) == 6 * 20 and {m["split"] for m in d["metrics"]} == {"tune", "held_out"}
    assert len(d["quality"]) == 6 and {"entity_preservation", "boundary_coherence", "recall_at_k", "k"} <= set(d["quality"][0])
    d1000 = client.get(f"{FAM}/snapshot", params={"budget_tokens": 1000}).json()
    assert d1000["grid"]["selected"]["budget_tokens"] == 1000 and d1000["grid"]["tune"]["frontier"]["budget_tokens"] == 1000
    assert client.get(f"{FAM}/snapshot", params={"budget_tokens": 777}).json()["grid"] is None


REPORT_KEYS = {"family", "title", "rows", "summary", "by_origin", "by_mode"}
ROW_KEYS = {"item_id", "split", "origin", "mode", "span_recall", "token_precision", "reciprocal_rank", "recall_at_k",
            "fully_covered", "note"}


def test_r3_report_uupt_is_heldout_report_of_selected_setting(client, world):
    """H-077: `report` = build_report(uupt) atas butir held-out pada setting terpilih; angka sama dengan metrik snapshot."""
    d = client.get(f"{FAM}/snapshot").json()
    r = d["report"]
    assert set(r) == REPORT_KEYS and r["family"] == "uupt" and r["title"] == "Held-out results"
    sel = d["grid"]["selected"]["setting_id"]
    held = sorted(m["item_id"] for m in d["metrics"] if m["setting_id"] == sel and m["split"] == "held_out")
    assert held and [x["item_id"] for x in r["rows"]] == held and len(held) == d["items_summary"]["by_split"]["held_out"]
    assert all(set(x) == ROW_KEYS and x["split"] == "held_out" for x in r["rows"])
    assert r["summary"]["n_items"] == len(held)
    assert set(r["summary"]["fully_covered"]) == {"numerator", "denominator", "text"}
    gold_rows = [x for x in r["rows"] if x["span_recall"] is not None]
    assert all(x["span_recall"]["text"] == f"{x['span_recall']['numerator']} of {x['span_recall']['denominator']}" for x in gold_rows)
    assert [x["note"] for x in r["rows"] if x["span_recall"] is None] == ["no gold (must abstain)"] * (len(held) - len(gold_rows))
    # budget lain -> setting terpilih lain, tetap laporan held-out
    d1 = client.get(f"{FAM}/snapshot", params={"budget_tokens": 1000}).json()
    assert d1["report"]["title"] == "Held-out results" and d1["report"]["rows"]
    # anggaran tanpa run -> grid null -> report null
    assert client.get(f"{FAM}/snapshot", params={"budget_tokens": 777}).json()["report"] is None


def test_r3_report_akta_is_null_and_not_a_heldout_claim(client):
    d = client.get("/api/families/akta/snapshot").json()
    assert d["grid"] is None and d["report"] is None  # tidak ada grid akta tersimpan (H-077)


def test_static_export_carries_report_and_passes_scanner(world, tmp_path):
    from backend.replay.export import build_files
    from backend.replay.scan import scan_files

    app = create_app(Service(tokenizer=get_tokenizer(), runs_dir=world["root"] / "runs", encoder=FakeEncoder(),
                             embed_cache_dir=world["root"] / "emb"), env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE},
                     model_config=model_cfg(), budget_config=budget_cfg(), replay=True)
    files = build_files(app, families=("uupt", "akta"), retrieval=False, answers=False)
    uupt = json.loads(files["snapshot/uupt/default.json"])
    assert uupt["report"] is not None and uupt["report"]["title"] == "Held-out results"
    assert uupt["report"] == client_report(world)
    assert json.loads(files["snapshot/akta/default.json"])["report"] is None
    assert scan_files(files, secrets=[K], base_urls=[BASE]) == []


def client_report(world):
    return world["client"].get(f"{FAM}/snapshot").json()["report"]


def test_r3_is_read_only(client, world):
    before = sorted(p.name for p in (world["root"] / "runs").rglob("*") if p.is_file())
    calls = world["enc"].encode_calls
    client.get(f"{FAM}/snapshot")
    assert sorted(p.name for p in (world["root"] / "runs").rglob("*") if p.is_file()) == before
    assert world["enc"].encode_calls == calls


# ---- R4 ----
def test_r4_chunks_for_grid_setting_and_unavailable_setting(client, world):
    r = client.get(f"{FAM}/docs/uupt-40-2007", params={"setting_id": sid(world, "fixed_size", "dense")})
    assert r.status_code == 200 and len(r.json()["chunks"]) == 103  # korpus beku, fixed_size berurutan (H-062)
    clean_error(client.get(f"{FAM}/docs/uupt-40-2007", params={"setting_id": sid(world, "structure_schema", "bm25")}), 422, "validation_failed")
    clean_error(client.get(f"{FAM}/docs/uupt-40-2007", params={"setting_id": "0" * 64}), 404, "not_found")


# ---- R5 ----
@pytest.mark.parametrize("chunker,mode", [("structure_handwritten", "bm25"), ("fixed_size", "dense"), ("structure_handwritten", "hybrid")])
def test_r5_retrieval_shape_and_agrees_with_grid_metrics(client, world, chunker, mode):
    s = sid(world, chunker, mode)
    r = client.get(f"{FAM}/retrieval", params={"setting_id": s, "item_id": "kontrol-K-02"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"retrieved_chunk_ids", "ranks", "scores", "packed_tokens"}
    n = len(d["retrieved_chunk_ids"])
    assert n > 0 and len(d["ranks"]) == n and len(d["scores"]) == n and d["ranks"] == sorted(d["ranks"]) and d["ranks"][0] == 1
    assert 0 < d["packed_tokens"] <= 2000
    env = next((world["root"] / "runs" / "grid").glob("*.json"))
    stored = next(m for m in json.loads(env.read_text(encoding="utf-8"))["metrics"] if m["setting_id"] == s and m["item_id"] == "kontrol-K-02")
    assert stored["retrieved_chunk_ids"] == d["retrieved_chunk_ids"] and stored["retrieved_tokens"] == d["packed_tokens"]


def test_r5_errors(client, world):
    ok = sid(world, "fixed_size", "bm25")
    clean_error(client.get(f"{FAM}/retrieval", params={"setting_id": "0" * 64, "item_id": "kontrol-K-02"}), 404, "not_found")
    clean_error(client.get(f"{FAM}/retrieval", params={"setting_id": ok, "item_id": "nope"}), 404, "not_found")
    clean_error(client.get(f"{FAM}/retrieval", params={"setting_id": sid(world, "fixed_size", "bm25", header=True), "item_id": "kontrol-K-02"}),
                422, "validation_failed")


# ---- R6 ----
def test_r6_lists_grid_run_records(client, world):
    rows = client.get("/api/runs", params={"kind": "grid"}).json()
    assert len(rows) == 1 and rows[0]["kind"] == "grid" and rows[0]["status"] == "ok" and rows[0]["cost_usd_micros"] == 0
    assert all(r["kind"] != "grid" for r in client.get("/api/runs", params={"kind": "measure"}).json())
    assert any(r["kind"] == "grid" for r in client.get("/api/runs").json())


# ---- replay: W1 hanya membaca ----
def test_w1_in_replay_reads_only(world, tmp_path):
    svc = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "empty")
    app = create_app(svc, env={}, model_config=model_cfg(), budget_config=budget_cfg(), replay=True)
    r = TestClient(app, raise_server_exceptions=False).post(f"{FAM}/grid/run", json={})
    clean_error(r, 409, "replay_no_stored_run")
    svc2 = Service(tokenizer=get_tokenizer(), runs_dir=world["root"] / "runs")
    app2 = create_app(svc2, env={}, model_config=model_cfg(), budget_config=budget_cfg(), replay=True)
    r2 = TestClient(app2, raise_server_exceptions=False).post(f"{FAM}/grid/run", json={})
    assert r2.status_code == 200 and r2.json()["status"] == "cached"
