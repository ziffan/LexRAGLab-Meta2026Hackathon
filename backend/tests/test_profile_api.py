"""M4.3 W7/W8 lewat HTTP: S13, S14, S18, S19, status galat W8; I-42 (tokenizer di chunker_key) dan I-43 (nama hash)."""

from __future__ import annotations

import dataclasses
import json
import re
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api.app import Service, create_app
from backend.chunking import fixed, schema_chunker, structure
from backend.chunking.fixed import chunk_fixed
from backend.tests import profile_helpers as H
from backend.tests.toy_ws import ToyWs

SECRETS = {"OPENROUTER_API_KEY": "sk-test-123", "META_API_KEY": "sk-meta-456"}


class Boom:
    """Transport Model API palsu: setiap pemakaian menggagalkan test."""

    def __getattr__(self, name):
        raise AssertionError("Model API must not be called")

    def __call__(self, *a, **k):
        raise AssertionError("Model API must not be called")


def make_client(tmp_path, deps=None, replay=False, env=None):
    app = create_app(Service(runs_dir=tmp_path / "runs"), env=env if env is not None else {}, replay=replay, spark_transport=Boom())
    app.state.profile_deps = deps or H.make_deps(tmp_path)
    return app, TestClient(app, raise_server_exceptions=False)


def url(family, sid):
    return f"/api/families/{family}/profiles/export" + (f"?setting_id={sid}" if sid is not None else "")


# ---------- S13 ----------
def test_s13_deterministic_file_header_no_side_effects(tmp_path):
    now = ["2026-10-27T10:00:00Z"]
    deps = H.make_deps(tmp_path, clock=lambda: now[0])
    app, c = make_client(tmp_path, deps)
    r1 = c.get(url("uupt", H.P1["setting_id"]))
    now[0] = H.T2
    r2 = c.get(url("uupt", H.P1["setting_id"]))
    assert r1.status_code == r2.status_code == 200
    assert re.fullmatch(r'attachment; filename="[^"]+\.json"', r1.headers["content-disposition"])
    assert r1.headers["x-replay"] == "false"
    assert r1.json()["created_at"] == H.T1 and r2.json()["created_at"] == H.T2
    assert r1.content.replace(H.T1.encode(), b"@") == r2.content.replace(H.T2.encode(), b"@")
    assert json.dumps(r1.json(), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") == r1.content  # kanonik
    path = tmp_path / "profiles" / "uupt" / f"{H.P1['setting_id']}.json"
    assert path.read_bytes() == r2.content
    assert not (tmp_path / "runs").exists()  # tanpa RunRecord


def test_s13_replay_serves_but_does_not_write(tmp_path):
    deps = H.make_deps(tmp_path)
    _, c = make_client(tmp_path, deps)
    c.get(url("uupt", H.P1["setting_id"]))
    path = tmp_path / "profiles" / "uupt" / f"{H.P1['setting_id']}.json"
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    time.sleep(0.02)
    later = dataclasses.replace(deps, clock=lambda: H.T2)
    _, rc = make_client(tmp_path, later, replay=True)
    r = rc.get(url("uupt", H.P1["setting_id"]))
    assert r.status_code == 200 and r.headers["x-replay"] == "true" and "content-disposition" in r.headers
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime
    # replay pada setting yang belum pernah diekspor: respons ada, berkas tetap tidak ada
    r = rc.get(url("uupt", H.P2["setting_id"]))
    assert r.status_code == 200 and not (tmp_path / "profiles" / "uupt" / f"{H.P2['setting_id']}.json").exists()


# ---------- S14 ----------
def test_s14_fields_and_types(tmp_path):
    deps = H.make_deps(tmp_path, packing="skip")
    _, c = make_client(tmp_path, deps)
    got = {n: c.get(url("uupt", s["setting_id"])).json() for n, s in (("P1", H.P1), ("PD", H.PD), ("PD2", H.PD2))}
    keys = {"profile_version", "family", "setting", "schema", "corpus_hash", "config_hash", "chunk_set_hash", "tokenizer",
            "clean_sha256", "loader_rules_version", "packing", "embedder", "held_out", "created_at"}
    for p in got.values():
        assert set(p) == keys and len(keys) == 14
        assert p["profile_version"] == "1" and p["packing"] == "skip" and p["schema"] is None
        assert p["tokenizer"] == {"name": "toy-ws", "version": "1"} and p["created_at"].endswith("Z")
        assert all(re.fullmatch(r"[0-9a-f]{64}", p[k]) for k in ("corpus_hash", "config_hash", "chunk_set_hash", "clean_sha256"))
        from backend.chunking.model import make_setting_id
        assert p["setting"]["setting_id"] == make_setting_id(p["setting"])
    assert got["P1"]["embedder"] is None
    assert got["PD"]["embedder"] == H.EMBEDDER and set(got["PD"]["embedder"]) == {"name", "revision", "max_seq_length"}
    assert got["PD2"]["setting"]["header_b"] is True and got["PD2"]["setting"]["retrieval_mode"] == "hybrid"
    assert got["PD2"]["embedder"] == H.EMBEDDER and got["PD2"]["setting"]["setting_id"] != got["PD"]["setting"]["setting_id"]


# ---------- S18 ----------
@pytest.mark.parametrize("fam,sid,status,code", [
    ("uupt", "f" * 64, 404, "not_found"), ("uupt", H.PA1["setting_id"], 404, "not_found"), ("uupt", None, 400, "invalid_request"),
    ("xyz", H.P1["setting_id"], 404, "not_found")])
def test_s18_errors(tmp_path, fam, sid, status, code):
    _, c = make_client(tmp_path)
    r = c.get(url(fam, sid))
    assert r.status_code == status and set(r.json()) == {"error"} and r.json()["error"]["code"] == code
    assert "Traceback" not in r.text and not (tmp_path / "profiles").exists()


def test_s18e_no_grid_result(tmp_path):
    deps = dataclasses.replace(H.make_deps(tmp_path), grid_metrics=lambda fam: None)
    _, c = make_client(tmp_path, deps)
    r = c.get(url("uupt", H.P1["setting_id"]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed" and not (tmp_path / "profiles").exists()


# ---------- S19 ----------
def test_s19_no_secrets_paths_or_corpus_text(tmp_path):
    items = [{**i, "query": "kueri uji rahasia", "gold_spans": [{"start": 0, "end": 5}]} for i in H.ITEMS]
    deps = H.make_deps(tmp_path, items=items)
    _, c = make_client(tmp_path, deps, env=SECRETS)
    blobs = [c.get(url("uupt", H.P1["setting_id"])).content, c.get(url("akta", H.PA1["setting_id"])).content]
    blobs += [p.read_bytes() for p in (tmp_path / "profiles").rglob("*.json")]
    assert len(blobs) == 4
    for b in blobs:
        t = b.decode("utf-8")
        for bad in ("sk-test-123", "sk-meta-456", "C:\\", "D:\\", "/home/", "/Users/", "a0 a1", "Aa bb", "kueri uji rahasia", "gold_spans"):
            assert bad not in t, bad


# ---------- W8 lewat HTTP ----------
def test_w8_statuses_and_no_write(tmp_path):
    deps = H.make_deps(tmp_path)
    _, c = make_client(tmp_path, deps)
    prof = c.get(url("uupt", H.P1["setting_id"])).json()
    before = H.tree(tmp_path)
    r = c.post("/api/profiles/import", json=prof)
    assert r.status_code == 200 and r.json() == {"ok": True, "chunk_set_hash_matches": True} and r.headers["x-replay"] == "false"
    bad = {**prof, "chunk_set_hash": "0" * 64}
    assert c.post("/api/profiles/import", json=bad).json() == {"ok": False, "chunk_set_hash_matches": False}
    r = c.post("/api/profiles/import", json={**prof, "corpus_hash": "0" * 64})
    assert r.status_code == 409 and r.json()["error"]["code"] == "hash_mismatch" and "Profile corpus hash does not match loaded corpus" in r.json()["error"]["message"]
    r = c.post("/api/profiles/import", json={**prof, "packing": "truncate_all"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    assert c.post("/api/profiles/import", json=[1]).status_code == 400
    assert H.tree(tmp_path) == before


# ---------- I-42 ----------
def test_i42_tokenizer_is_part_of_every_chunker_key():
    """Kunci cache potongan (`runs/chunks/`, ARCH §8) diturunkan dari `chunker_key`; tokenizer (nama + versi) harus ikut di semua chunker."""
    cfg = config.load("retrieval")
    a, b = ToyWs(), H.ToyWs2()
    assert fixed.fixed_key(cfg, 4, 1, a) != fixed.fixed_key(cfg, 4, 1, b)
    assert structure.structure_key(cfg, a) != structure.structure_key(cfg, b)
    rec = {"family": "akta", "schema_version": 1, "body": H.V1_BODY}
    assert schema_chunker.schema_key(cfg, rec, a) != schema_chunker.schema_key(cfg, rec, b)
    other_name = SimpleNamespace(info=SimpleNamespace(name="toy-other", version="1"))
    assert fixed.fixed_key(cfg, 4, 1, a) != fixed.fixed_key(cfg, 4, 1, other_name)  # nama saja pun cukup
    # akibatnya: span sama, tokenizer beda -> chunk_id beda
    text = " ".join(f"w{i}" for i in range(8))
    doc = SimpleNamespace(doc_id="dx", text=text, sections=[{"section": "batang_tubuh", "start": 0, "end": len(text)}], metadata={},
                          clean_sha256="x" * 64)
    ca, cb = (chunk_fixed(doc, size=4, overlap=1, retrieval_cfg=cfg, tokenizer=t) for t in (a, b))
    assert [(c.start, c.end) for c in ca] == [(c.start, c.end) for c in cb]
    assert {c.chunk_id for c in ca}.isdisjoint({c.chunk_id for c in cb})


# ---------- I-43 ----------
def test_i43_two_hash_functions_have_distinct_names():
    from backend.retrieval import dense

    assert not hasattr(dense, "chunk_set_hash") and callable(dense.embedding_set_hash)
    enc = SimpleNamespace(model="m", revision="r", max_seq_length=8)
    items = [("c1", "a"), ("c2", "b")]
    # nilai kunci cache embedding tak berubah: hash kanonik (model, revisi, max_seq_length, daftar terurut menurut chunk_id)
    from backend.chunking.model import sha256_hex

    assert dense.embedding_set_hash(enc, items[::-1]) == sha256_hex(
        {"model": "m", "revision": "r", "max_seq_length": 8, "items": [["c1", "a"], ["c2", "b"]]})
    # hash profil beda tujuan: tanpa data encoder
    from backend.profile.hashing import profile_chunk_set_hash

    rows = [("d", 0, 1, "c1", "a"), ("d", 1, 2, "c2", "b")]
    assert profile_chunk_set_hash(rows) == sha256_hex([["c1", "a"], ["c2", "b"]]) != dense.embedding_set_hash(enc, items)


# ---------- SHOULD-1: skema tertanam cacat -> 422 (bukan 500) ----------
def _schema_mut_drop_levels(s):
    del s["levels"]


def _schema_mut_str_level(s):
    s["levels"] = ["x"]


def _schema_mut_level_order_only(s):
    s["levels"] = [{"order": 1}]


@pytest.mark.parametrize("mutate", [_schema_mut_drop_levels, _schema_mut_str_level, _schema_mut_level_order_only],
                         ids=["no_levels", "levels_str", "level_order_only"])
def test_should1_malformed_embedded_schema_is_422_over_http(tmp_path, mutate):
    _, c = make_client(tmp_path)
    prof = c.get(url("akta", H.PA1["setting_id"])).json()
    assert c.post("/api/profiles/import", json=prof).json() == {"ok": True, "chunk_set_hash_matches": True}  # kontrol
    mutate(prof["schema"])
    before = H.tree(tmp_path)
    r = c.post("/api/profiles/import", json=prof)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed" and "schema" in r.json()["error"]["message"]
    assert "Traceback" not in r.text and H.tree(tmp_path) == before


# ---------- SHOULD-4: butir grid tak dikenal -> 422 ----------
def test_should4_unknown_grid_item_is_422(tmp_path):
    items = [i for i in H.ITEMS if i["id"] != "h1"]  # ItemMetrics merujuk h1 yang tak ada di daftar butir
    _, c = make_client(tmp_path, H.make_deps(tmp_path, items=items))
    r = c.get(url("uupt", H.P1["setting_id"]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed" and "unknown item" in r.json()["error"]["message"]
    assert not (tmp_path / "profiles").exists()


# ---------- W12: build_deps nyata memuat akta dari config/corpus_akta.toml ----------
def test_w12_real_deps_serve_deed_family(tmp_path):
    from backend.grid.expand import expand_grid

    svc = Service(runs_dir=tmp_path / "runs")
    app = create_app(svc, env={}, replay=False, spark_transport=Boom())  # tanpa profile_deps: jalur build_deps
    c = TestClient(app, raise_server_exceptions=False)
    sid = next(iter(expand_grid(svc.cfg("grid"), "akta"))).setting_id
    r = c.get(url("akta", sid))
    assert r.status_code == 200, r.text  # bukan 422 "No corpus is loaded"
    prof = r.json()
    assert prof["family"] == "akta" and len(prof["corpus_hash"]) == 64
    ok = c.post("/api/profiles/import", json=prof)
    assert ok.status_code == 200 and ok.json()["ok"] is True  # corpus_hash tidak ditolak
    prof["corpus_hash"] = "0" * 64
    bad = c.post("/api/profiles/import", json=prof)
    assert bad.status_code == 409 and "corpus hash" in bad.json()["error"]["message"]
