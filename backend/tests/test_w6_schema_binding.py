"""W19: `Service` membawa `SchemaBinding` (H-075) ke W6, R4 `setting_id`, R5, `stored_grid`/W1 dan pipeline, seperti
`grid_run --with-schema`. Skema A sintetis di store sementara, korpus UU 40/2007, transport Spark palsu. Tanpa jaringan."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.grid.expand import expand_grid
from backend.grid.schemas import SchemaBinding
from backend.pipeline.grid_run import baseline_for, make_plan
from backend.schema_a import SchemaStore
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import Clock, FakeTransport, Resp, body_ok, budget_cfg, env_ok, model_cfg

ANS = "/api/families/uupt/answers"
DOC = "/api/families/uupt/docs/uupt-40-2007"
RET = "/api/families/uupt/retrieval"
ITEM = "kontrol-K-02"
JAWAB = {"status": "jawab", "jawaban": "Direktur dapat meminta RUPS.",
         "kutipan": [{"alamat": "UU 40/2007 › Pasal 78 › ayat (2)", "teks": "x"}]}
PASAL, AYAT = r"^###\s+Pasal\s+\d+", r"^\(\d+\)"


def lv(order, name, parent, pattern, unit):
    return {"order": order, "name": name, "parent_order": parent, "marker_pattern": pattern, "is_chunk_unit": unit, "examples": []}


def schema_rec(unit_level=1):
    levels = [lv(1, "pasal", None, PASAL, unit_level == 1), lv(2, "ayat", 1, AYAT, unit_level == 2)]
    return {"source": "spark", "parent_version": None, "validation": [], "run_id": None, "created_at": "2026-10-27T00:00:00Z",
            "operator_note": None, "sample": [], "body": {"family": "uupt", "default_chunk_level": unit_level, "levels": levels}}


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("w19")
    s = Service(tokenizer=get_tokenizer(), runs_dir=root / "runs", encoder=FakeEncoder(), embed_cache_dir=root / "emb")
    s.doc("uupt-40-2007")
    return s


def make(base, tmp_path, *, schema=True, replay=False):
    runs = tmp_path / "runs"
    if schema:
        SchemaStore(runs).append("uupt", schema_rec())
    tr = FakeTransport(Clock(), None, Resp(200, body_ok(JAWAB)))
    s = Service(tokenizer=base.tokenizer, runs_dir=runs, encoder=base._encoder, embed_cache_dir=base.embed_cache_dir)
    s._docs = base._docs
    app = create_app(s, env=env_ok(), model_config=model_cfg(), budget_config=budget_cfg(), replay=replay, spark_transport=tr.transport)
    return TestClient(app, raise_server_exceptions=False), tr, s


def schema_pair(svc, mode="bm25", budget=2000):
    ss = svc.grid_settings("uupt")
    best = next(s for s in ss if s.chunker == "structure_schema" and s.retrieval_mode == mode and s.budget_tokens == budget and not s.header_b)
    return best, baseline_for(ss, best, svc.cfg("grid")["baseline"])


def body(best, base_, **over):
    return {"item_id": ITEM, "best_setting_id": best.setting_id, "baseline_setting_id": base_.setting_id,
            "model_profile": "meta", "live": True, **over}


def tree(root):
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in sorted(root.rglob("*")) if p.is_file()}


# ---------- tanpa skema: perilaku lama ----------
def test_without_schema_store_structure_schema_stays_422_with_old_message(base, tmp_path):
    c, tr, svc = make(base, tmp_path, schema=False)
    assert svc.schema_binding() is None
    best, bl = schema_pair(svc)
    assert best.schema_version is None
    r = c.post(ANS, json=body(best, bl))
    assert r.status_code == 422 and "needs schema A" in r.json()["error"]["message"] and tr.calls == 0
    r = c.get(RET, params={"setting_id": best.setting_id, "item_id": ITEM})
    assert r.status_code == 422 and "needs schema A" in r.json()["error"]["message"]
    r = c.get(DOC, params={"setting_id": best.setting_id})
    assert r.status_code == 422 and "needs schema A" in r.json()["error"]["message"]


# ---------- dengan skema ----------
def test_setting_ids_match_grid_with_schema_binding(base, tmp_path):
    _c, _tr, svc = make(base, tmp_path)
    plan = make_plan("uupt", doc=svc.doc("uupt-40-2007"), tokenizer=svc.tok(), butir_dir=svc.butir_dir, runs_dir=svc.runs_dir,
                     create_split=False, schemas=SchemaBinding.from_store(svc.runs_dir, "uupt"))
    ids = {s.setting_id for s in plan.settings}
    assert {s.setting_id for s in svc.grid_settings("uupt")} == ids
    assert {x["setting_id"] for x in svc.settings("uupt")} == ids
    assert schema_pair(svc)[0].schema_version == 1


def test_w6_structure_schema_builds_context_from_schema_chunks(base, tmp_path):
    c, tr, svc = make(base, tmp_path)
    best, bl = schema_pair(svc)
    r = c.post(ANS, json=body(best, bl))
    assert r.status_code == 200, r.text
    d = r.json()
    assert tr.calls == 2 and d["best"]["setting_id"] == best.setting_id and d["best"]["context_chunk_ids"]
    doc = svc.doc("uupt-40-2007")
    schema_ids = {x["chunk_id"] for x in svc.schema_chunks(doc, 1)}
    assert set(d["best"]["context_chunk_ids"]) <= schema_ids          # potongan skema (unit = Pasal)
    assert not set(d["baseline"]["context_chunk_ids"]) & schema_ids  # kolom baseline tetap fixed_size


def test_r4_and_r5_with_schema_setting_id(base, tmp_path):
    c, _tr, svc = make(base, tmp_path)
    best, _ = schema_pair(svc)
    doc = svc.doc("uupt-40-2007")
    r4 = c.get(DOC, params={"setting_id": best.setting_id})
    assert r4.status_code == 200, r4.text
    assert r4.json()["chunks"] == svc.schema_chunks(doc, 1)
    r5 = c.get(RET, params={"setting_id": best.setting_id, "item_id": ITEM})
    assert r5.status_code == 200, r5.text
    j = r5.json()
    assert j["retrieved_chunk_ids"] and set(j["retrieved_chunk_ids"]) <= {x["chunk_id"] for x in r4.json()["chunks"]}
    # setting_id lama (tanpa versi terikat) tak dikenal lagi setelah skema ada: sama seperti grid
    old = next(s for s in expand_grid(svc.cfg("grid"), "uupt") if s.chunker == "structure_schema")
    assert c.get(DOC, params={"setting_id": old.setting_id}).status_code == 404


def test_new_schema_version_changes_setting_and_rebuilds_pipeline(base, tmp_path):
    c, _tr, svc = make(base, tmp_path)
    doc = svc.doc("uupt-40-2007")
    best1, _ = schema_pair(svc)
    p1 = svc.pipeline()
    ch1 = {x["chunk_id"] for x in svc.chunks(doc, best1)}
    SchemaStore(svc.runs_dir).append("uupt", schema_rec(unit_level=2))  # v2 aktif (unit = ayat)
    best2, _ = schema_pair(svc)
    assert best2.schema_version == 2 and best2.setting_id != best1.setting_id
    assert svc.pipeline() is not p1
    assert ch1 != {x["chunk_id"] for x in svc.chunks(doc, best2)}
    assert c.get(DOC, params={"setting_id": best1.setting_id}).status_code == 404


def test_stored_grid_and_replay_are_read_only_and_use_schema_key(base, tmp_path):
    c, tr, svc = make(base, tmp_path, replay=True)
    before = tree(svc.runs_dir)
    plan_s, env = svc.stored_grid("uupt")
    assert env is None and plan_s.schemas is not None and plan_s.config_hash != svc.plan("uupt").config_hash  # hash memuat identitas skema
    best, bl = schema_pair(svc)
    r = c.post(ANS, json=body(best, bl, live=False))
    assert r.status_code == 409 and r.json()["error"]["code"] == "replay_no_stored_run" and tr.calls == 0
    assert tree(svc.runs_dir) == before                                # store skema dan runs/ tak berubah


def test_w1_grid_run_with_schema_is_found_by_r3(base, tmp_path):
    _c, _tr, svc = make(base, tmp_path)
    res = svc.run_grid("uupt")
    ran = [s for s in res.envelope["settings_run"] if s["chunker"] == "structure_schema"]
    assert ran and all(s["schema_version"] == 1 for s in ran)
    _plan, env = svc.stored_grid("uupt")
    assert env is not None and env["key"] == res.key
    assert schema_pair(svc)[0].setting_id in {s["setting_id"] for s in ran}


def test_header_binding_coexists_with_schema_binding(base, tmp_path):
    _c, _tr, svc = make(base, tmp_path)

    def respond(_tr, request):
        b = json.loads(request.content.decode("utf-8"))
        cid = re.search(r"chunk_id: (\S+)", b["input"]).group(1)
        return Resp(200, body_ok({"chunk_id": cid, "header": "Konteks singkat"}))

    tr2 = FakeTransport(Clock(), default=respond)
    c2 = TestClient(create_app(svc, env=env_ok(), model_config=model_cfg(), budget_config=budget_cfg(), spark_transport=tr2.transport),
                    raise_server_exceptions=False)
    r = c2.post("/api/families/uupt/headers/run", json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 2})
    assert r.status_code == 200, r.text
    assert svc.header_binding() is not None and svc.schema_binding() is not None
    pipe = svc.pipeline()
    assert pipe.headers is not None and pipe.schemas is not None
    best, _ = schema_pair(svc)
    assert c2.get(RET, params={"setting_id": best.setting_id, "item_id": ITEM}).status_code == 200
