"""W14: R4 `schema_version` (potongan akta menurut skema A tersimpan) dan ekspor statisnya. Skema sintetis di store sementara;
tanpa jaringan dan tanpa Model API."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.replay.export import build_files
from backend.schema_a import SchemaStore

from ._chunk_util import ToyWs
from .test_akta_m41 import body

URL = "/api/families/akta/docs/akta-01"


def rec(b):
    return {"source": "spark", "parent_version": None, "body": b, "validation": [], "run_id": None,
            "created_at": "2026-10-27T00:00:00Z", "operator_note": None, "sample": []}


@pytest.fixture()
def world(tmp_path):
    runs = tmp_path / "runs"
    st = SchemaStore(runs)
    st.append("akta", rec(body()))                       # v1: Pasal sebagai unit
    bad = body()
    bad["default_chunk_level"] = 9                        # v2: tak valid untuk dokumen
    st.append("akta", rec(bad))
    svc = Service(tokenizer=ToyWs(), runs_dir=runs)
    return svc, TestClient(create_app(svc), raise_server_exceptions=False)


def test_without_param_unchanged(world):
    _svc, c = world
    j = c.get(URL).json()
    assert j["chunks"] is None and j["headers"] is None and j["text"]
    assert set(j) == {"doc_id", "text", "chunks", "headers"}


def test_schema_version_returns_schema_chunks(world):
    svc, c = world
    r = c.get(URL, params={"schema_version": 1})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["chunks"] == svc.schema_chunks(svc.doc("akta-01"), 1) and len(j["chunks"]) >= 3
    assert [x["address"] for x in j["chunks"]][:2] == ["Akta 01 › Pasal 1", "Akta 01 › Pasal 2"]
    assert j["text"] == c.get(URL).json()["text"] and j["headers"] is None


def test_missing_version_404_invalid_schema_422(world):
    _svc, c = world
    r = c.get(URL, params={"schema_version": 7})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = c.get(URL, params={"schema_version": 2})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed"
    assert c.get("/api/families/uupt/docs/akta-01", params={"schema_version": 1}).status_code == 404  # keluarga tak cocok


def test_schema_version_with_setting_id_is_400_and_junk_is_rejected(world):
    _svc, c = world
    r = c.get(URL, params={"schema_version": 1, "setting_id": "x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"
    assert c.get(URL, params={"schema_version": "abc"}).status_code in (400, 422)


def test_export_includes_schema_versions(tmp_path):
    runs = tmp_path / "runs"
    SchemaStore(runs).append("akta", rec(body()))
    svc = Service(tokenizer=ToyWs(), runs_dir=runs)
    app = create_app(svc, replay=True)
    files = build_files(app, families=("akta",), retrieval=False, answers=False)
    key = "docs/akta/akta-01/schema-v1.json"
    assert key in files and "docs/akta/akta-01/_text.json" in files
    part = json.loads(files[key])
    assert set(part) == {"doc_id", "chunks", "headers"} and len(part["chunks"]) >= 3
    assert part["chunks"] == svc.schema_chunks(svc.doc("akta-01"), 1)
    assert all(f"docs/akta/akta-0{i}/schema-v1.json" in files for i in range(1, 6))
    assert "docs/akta/akta-01/schema-v2.json" not in files
    # tanpa skema: tidak ada berkas skema
    empty = build_files(create_app(Service(tokenizer=ToyWs(), runs_dir=tmp_path / "none"), replay=True), families=("akta",), retrieval=False, answers=False)
    assert not [k for k in empty if "schema-v" in k]
