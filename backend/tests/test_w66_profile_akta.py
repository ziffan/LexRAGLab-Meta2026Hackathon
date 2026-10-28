"""W66: profil akta (M4.3, H-077, H-078, H-091): ekspor W7 keluarga multi-dokumen, round-trip W8 untuk kelima akta, dan
`config_hash` akta = identitas config keluarga + peta unit (UU PT tetap hash umum). Tanpa jaringan, tanpa Model API;
`runs/` hanya dibaca, `profiles/` ditulis ke tmp."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.api.routers.profiles import build_deps
from backend.pipeline.grid_run import CONFIGS, FAMILY_CONFIGS, pipeline_config_hash, unit_map_identity
from backend.profile.hashing import chunk_rows, clean_text_hash, corpus_hash

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = sorted((ROOT / "profiles" / "akta").glob("*.json"))
pytestmark = pytest.mark.skipif(not COMMITTED, reason="no committed akta profile")


def _app(tmp_path):
    app = create_app(Service(runs_dir=ROOT / "runs"), env={}, replay=True, spark_transport=None)
    app.state.profiles_dir = tmp_path / "profiles"
    return app, TestClient(app, raise_server_exceptions=False)


def _load():
    p = COMMITTED[0]
    return p, json.loads(p.read_text(encoding="utf-8"))


def test_committed_profile_shape_and_lf():
    p, prof = _load()
    assert b"\r" not in p.read_bytes() and p.stem == prof["setting"]["setting_id"]
    assert prof["family"] == "akta" and prof["held_out"] is None
    s = prof["setting"]
    assert (s["chunker"], s["schema_version"], s["retrieval_mode"], s["header_b"], s["budget_tokens"]) == (
        "structure_schema", 2, "dense", False, 2000)
    assert prof["schema"]["family"] == "akta" and prof["loader_rules_version"] == "akta-1"


def test_w7_export_equals_committed_except_created_at(tmp_path):
    p, com = _load()
    _, c = _app(tmp_path)
    r = c.get(f"/api/families/akta/profiles/export?setting_id={com['setting']['setting_id']}")
    assert r.status_code == 200, r.text
    a, b = r.json(), dict(com)
    assert a.pop("created_at") and b.pop("created_at")
    assert a == b


def test_hashes_cover_all_five_akta_and_config_hash_is_akta_identity(tmp_path):
    _, com = _load()
    app, _ = _app(tmp_path)

    class Req:
        pass

    req = Req()
    req.app = app
    deps = build_deps(req)
    docs = deps.docs("akta")
    assert [d.doc_id for d in docs] == [f"akta-0{i}" for i in range(1, 6)]
    assert com["corpus_hash"] == corpus_hash(docs) and com["clean_sha256"] == clean_text_hash(docs)
    svc = app.state.service
    cfgs = {n: svc.cfg(n) for n in (*CONFIGS, *FAMILY_CONFIGS["akta"])}
    expect = pipeline_config_hash(cfgs, deps.tokenizer.info, unit_map=unit_map_identity(cfgs, svc.schema_binding("akta")))
    assert com["config_hash"] == expect
    assert com["config_hash"] != pipeline_config_hash({n: svc.cfg(n) for n in CONFIGS}, deps.tokenizer.info)
    # UU PT tetap hash umum
    assert deps.config_hash_for("uupt") == deps.config_hash


def test_w8_roundtrip_identical_chunks_for_five_akta(tmp_path):
    _, com = _load()
    app, c = _app(tmp_path)

    class Req:
        pass

    req = Req()
    req.app = app
    deps = build_deps(req)
    docs = deps.docs("akta")
    schema_record = {"family": "akta", "schema_version": 2, "body": com["schema"]}
    from backend.profile.service import SETTING_FIELDS

    content = {k: com["setting"][k] for k in SETTING_FIELDS}
    by_doc = {d.doc_id: list(deps.chunker(d, content, schema_record, deps.tokenizer)) for d in docs}
    again = {d.doc_id: list(deps.chunker(d, content, schema_record, deps.tokenizer)) for d in docs}
    assert all(len(v) >= 1 for v in by_doc.values()) and len(by_doc) == 5
    assert chunk_rows(docs, by_doc) == chunk_rows(docs, again)
    assert {k: [(x.chunk_id, x.start, x.end) for x in v] for k, v in by_doc.items()} == {
        k: [(x.chunk_id, x.start, x.end) for x in v] for k, v in again.items()}
    ok = c.post("/api/profiles/import", json=com)
    assert ok.status_code == 200 and ok.json() == {"ok": True, "chunk_set_hash_matches": True}


def test_w8_tampered_akta_profile_rejected(tmp_path):
    _, com = _load()
    _, c = _app(tmp_path)
    bad = dict(com, chunk_set_hash="0" * 64)
    r = c.post("/api/profiles/import", json=bad)
    assert r.status_code == 200 and r.json()["ok"] is False
    bad2 = dict(com, corpus_hash="0" * 64)
    assert c.post("/api/profiles/import", json=bad2).status_code == 409
    # held_out non-null untuk akta ditolak (A13)
    bad3 = dict(com, held_out={"n_items": 1, "by_origin": {"operator": 1, "spark_disetujui": 0}, "mean_span_recall": 1.0,
                               "mean_token_precision": 1.0, "fully_covered": {"covered": 1, "total": 1}})
    assert c.post("/api/profiles/import", json=bad3).status_code == 422
