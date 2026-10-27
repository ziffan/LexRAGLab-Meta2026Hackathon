"""M3.3 W2 dan W9 lewat transport palsu dan layanan palsu (korpus sintetis). Tanpa jaringan, tanpa Model API."""

from __future__ import annotations

import copy
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.errors import ApiError

from .spark_fakes import Clock, FakeTransport, Resp, body_ok, budget_cfg, env_ok, model_cfg, scan_runs_dir
from .test_schema_a_core import CS, SAMPLE, good_body

W2 = "/api/families/uupt/schemas/induce"


def doc(doc_id="doc-sintetis", family="uupt", text=SAMPLE, clean=CS):
    return SimpleNamespace(doc_id=doc_id, family=family, text=text, sha256="s" * 64, clean_sha256=clean,
                           loader_rules_version="1")


class FakeService:
    def __init__(self, runs_dir, docs=None):
        self.runs_dir = runs_dir
        self.docs = {d.doc_id: d for d in (docs if docs is not None else [doc()])}

    def doc(self, doc_id):
        if doc_id not in self.docs:
            raise ApiError(404, "not_found", f"Unknown doc_id {doc_id!r}.")
        return self.docs[doc_id]

    def tok(self):
        return SimpleNamespace(info=SimpleNamespace(name="tok-fake", version="0"), count=lambda t: len(t.split()))


def make(tmp_path, output=None, *, replay=False, budget=None, docs=None, script=None):
    tr = FakeTransport(Clock(), script, Resp(200, body_ok(output if output is not None else good_body())))
    svc = FakeService(tmp_path / "runs", docs)
    app = create_app(svc, env=env_ok(), model_config=model_cfg(), budget_config=budget or budget_cfg(), replay=replay,
                     spark_transport=tr.transport)
    return TestClient(app, raise_server_exceptions=False), tr, svc


def vpath(tmp_path, v):
    return tmp_path / "runs" / "schemas" / "uupt" / f"v{v}.json"


def correct_url(v):
    return f"/api/families/uupt/schemas/{v}/correct"


def test_w2_saves_v1_then_cache_hit_adds_no_version(tmp_path):
    c, tr, _ = make(tmp_path)
    r = c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r.status_code == 200, r.text
    j = r.json()
    rec = j["schema_record"]
    assert rec["schema_version"] == 1 and rec["source"] == "spark" and rec["parent_version"] is None
    assert rec["body"] == good_body() and rec["run_id"] == j["run"]["run_id"] and j["run"]["kind"] == "spark_a"
    assert vpath(tmp_path, 1).is_file() and tr.calls == 1
    r2 = c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r2.status_code == 200 and tr.calls == 1
    assert r2.json()["schema_record"]["schema_version"] == 1 and r2.json()["run"]["status"] == "cached"
    assert not vpath(tmp_path, 2).exists()
    assert scan_runs_dir(tmp_path / "runs") == []


def test_w2_request_validation(tmp_path):
    c, tr, _ = make(tmp_path)
    assert c.post(W2, json={"sample_doc_ids": []}).status_code == 422
    assert c.post(W2, json={"sample_doc_ids": ["doc-sintetis", "doc-sintetis"]}).status_code == 422
    assert c.post(W2, json={"sample_doc_ids": "doc-sintetis"}).status_code == 400
    assert c.post(W2, json={"sample_doc_ids": ["a"], "x": 1}).status_code == 400
    assert c.post(W2, json=[1]).status_code == 400
    assert c.post("/api/families/xx/schemas/induce", json={"sample_doc_ids": ["doc-sintetis"]}).status_code == 400
    r = c.post(W2, json={"sample_doc_ids": ["tak-ada"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    c2, _, _ = make(tmp_path / "b", docs=[doc(family="akta")])
    assert c2.post(W2, json={"sample_doc_ids": ["doc-sintetis"]}).status_code == 422
    assert tr.calls == 0


def test_w2_semantic_invalid_output_is_422_and_stores_nothing(tmp_path):
    bad = good_body()
    bad["levels"][1]["examples"] = ["Klausul 77"]
    c, tr, _ = make(tmp_path, bad)
    r = c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "schema_invalid"
    assert not vpath(tmp_path, 1).exists()
    from backend.schema_a import SchemaStore
    rej = SchemaStore(tmp_path / "runs").list_rejected("uupt")
    assert len(rej) == 1 and rej[0]["body"] == bad
    # RunRecord error tercatat di runs/spark/records
    recs = list((tmp_path / "runs" / "spark" / "records").glob("*.json"))
    assert len(recs) == 1 and "semantic_invalid" in recs[0].read_text(encoding="utf-8")


def test_w2_budget_exceeded_before_network(tmp_path):
    c, tr, _ = make(tmp_path, budget=budget_cfg(total=1, role=1))
    r = c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r.status_code == 402 and r.json()["error"]["code"] == "budget_exceeded" and tr.calls == 0


def test_w2_provider_error_maps_to_model_error(tmp_path):
    c, _, _ = make(tmp_path, script=[Resp(500, {"error": {"message": "boom"}})])
    r = c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r.status_code == 502 and r.json()["error"]["code"] == "model_error"
    assert not vpath(tmp_path, 1).exists()


def test_w2_replay_reads_only(tmp_path):
    c, tr, _ = make(tmp_path / "x", replay=True)
    r = c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "replay_no_stored_run" and tr.calls == 0
    live, _, _ = make(tmp_path)
    assert live.post(W2, json={"sample_doc_ids": ["doc-sintetis"]}).status_code == 200
    rep, tr2, _ = make(tmp_path, replay=True)
    r2 = rep.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert r2.status_code == 200 and r2.json()["schema_record"]["schema_version"] == 1 and tr2.calls == 0
    assert r2.json()["run"]["status"] == "replay"
    assert rep.post(correct_url(1), json={"schema": good_body()}).status_code == 400  # replay: tulis ditolak


def test_w9_creates_new_version_without_touching_v1(tmp_path):
    c, tr, _ = make(tmp_path)
    c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    before = vpath(tmp_path, 1).read_bytes()
    nb = good_body(notes="koreksi operator")
    r = c.post(correct_url(1), json={"schema": nb, "operator_note": "uji"})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["schema_version"] == 2 and rec["source"] == "operator" and rec["parent_version"] == 1
    assert rec["body"] == nb and rec["operator_note"] == "uji" and rec["run_id"] is None
    assert rec["sample_checked"] is True and rec["validation"]
    assert vpath(tmp_path, 1).read_bytes() == before and tr.calls == 1  # W9 tanpa Spark
    r3 = c.post(correct_url(2), json={"schema": nb})
    assert r3.status_code == 200 and r3.json()["schema_version"] == 3 and r3.json()["parent_version"] == 2
    r4 = c.post(correct_url(1), json={"schema": nb, "operator_note": None})  # induk lama tetap sah: versi baru lagi
    assert r4.json()["schema_version"] == 4 and r4.json()["parent_version"] == 1


def test_w9_invalid_schema_is_422_schema_invalid_and_stores_nothing(tmp_path):
    c, _, _ = make(tmp_path)
    c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    broken = copy.deepcopy(good_body())
    broken["levels"][0]["marker_pattern"] = "("
    fabricated = copy.deepcopy(good_body())
    fabricated["levels"][1]["examples"] = ["Klausul 99"]
    wrong_shape = {"family": "uupt", "levels": "x", "default_chunk_level": 1, "notes": None}
    extra = {**good_body(), "tambahan": 1}
    for bad in (broken, fabricated, wrong_shape, extra, "bukan objek", None):
        r = c.post(correct_url(1), json={"schema": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "schema_invalid", (bad, r.text)
    assert not vpath(tmp_path, 2).exists()


def test_w9_error_codes(tmp_path):
    c, _, _ = make(tmp_path)
    assert c.post(correct_url(1), json={"schema": good_body()}).status_code == 404  # belum ada v1
    c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    assert c.post(correct_url(7), json={"schema": good_body()}).status_code == 404
    assert c.post(correct_url("a"), json={"schema": good_body()}).status_code == 400
    assert c.post(correct_url(1), json={}).status_code == 400
    assert c.post(correct_url(1), json={"schema": good_body(), "x": 1}).status_code == 400
    assert c.post(correct_url(1), json={"schema": good_body(), "operator_note": 5}).status_code == 400
    assert c.post(correct_url(1), json={"schema": good_body(), "operator_note": "x" * 2001}).status_code == 400
    assert c.post("/api/families/xx/schemas/1/correct", json={"schema": good_body()}).status_code == 400
    assert not vpath(tmp_path, 2).exists()


def test_w9_sample_changed_is_hash_mismatch_and_missing_doc_skips_check(tmp_path):
    c, _, svc = make(tmp_path)
    c.post(W2, json={"sample_doc_ids": ["doc-sintetis"]})
    svc.docs["doc-sintetis"] = doc(clean="e" * 64)
    r = c.post(correct_url(1), json={"schema": good_body()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "hash_mismatch"
    del svc.docs["doc-sintetis"]
    r2 = c.post(correct_url(1), json={"schema": good_body()})
    assert r2.status_code == 200 and r2.json()["sample_checked"] is False
