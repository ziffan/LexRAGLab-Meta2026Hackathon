"""M3.1 W3 `POST /api/families/uupt/headers/run` lewat transport palsu. Korpus nyata; tanpa jaringan."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.tokenizer import get_tokenizer

from .spark_fakes import Clock, FakeTransport, Resp, body_ok, budget_cfg, env_ok, model_cfg

URL = "/api/families/uupt/headers/run"


def respond(tr, request):
    body = json.loads(request.content.decode("utf-8"))
    cid = re.search(r"chunk_id: (\S+)", body["input"]).group(1)
    return Resp(200, body_ok({"chunk_id": cid, "header": "Konteks singkat"}))


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    s = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path_factory.mktemp("m31") / "runs")
    s.doc("uupt-40-2007")
    return s


def make(svc, tmp_path, *, replay=False, budget=None):
    tr = FakeTransport(Clock(), default=respond)
    s = Service(tokenizer=svc.tokenizer, runs_dir=tmp_path / "runs")
    s._docs = svc._docs
    app = create_app(s, env=env_ok(), model_config=model_cfg(), budget_config=budget or budget_cfg(), replay=replay,
                     spark_transport=tr.transport)
    return TestClient(app, raise_server_exceptions=False), tr, s


def test_ayat_sample_then_cache_hit(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    r = c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 2})
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["headers"]) == 2 and len(j["runs"]) == 3 and isinstance(j["projection_usd_micros"], int)
    assert {h["granularity"] for h in j["headers"]} == {"ayat"} and all(h["header"] for h in j["headers"])
    assert tr.calls == 3 and tr.max_active == 1
    r2 = c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 2})
    assert r2.status_code == 200 and tr.calls == 3
    assert {x["status"] for x in r2.json()["runs"]} == {"cached"}


def test_pasal_shares_header_across_chunks(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    r = c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "pasal", "sample": 3})
    assert r.status_code == 200
    j = r.json()
    assert tr.calls == 4 and len(j["headers"]) >= 3  # pemanas + 3 Pasal; header per chunk_id penerima


def test_fixed_size_chunker(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    r = c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "ayat", "chunker": "fixed_size", "sample": 2})
    assert r.status_code == 200 and {h["granularity"] for h in r.json()["headers"]} == {"fixed_size"}


def test_errors(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    assert c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "bab"}).status_code == 400
    assert c.post(URL, json={"doc_id": "tidak-ada", "granularity": "ayat", "sample": 1}).status_code == 404
    assert c.post("/api/families/akta/headers/run", json={"doc_id": "x", "granularity": "ayat"}).status_code == 422
    assert tr.calls == 0


def test_budget_exceeded_before_network(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, budget=budget_cfg(total=10, role=10))
    r = c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 2})
    assert r.status_code == 402 and r.json()["error"]["code"] == "budget_exceeded" and tr.calls == 0


def test_replay_without_stored_run(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, replay=True)
    r = c.post(URL, json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "replay_no_stored_run" and tr.calls == 0
