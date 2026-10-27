"""H-079: versi prompt B dari config sampai ke binding grid; W3 meneruskan `schema_max_length_chars`. Tanpa jaringan."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend import config as bc
from backend.api.app import Service, create_app
from backend.grid.headers import HeaderBinding
from backend.header_b.prompt import header_schema, load_prompt
from backend.pipeline.grid_run import load_header_binding, run_family_grid
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir
from .spark_fakes import Clock, FakeTransport, Resp, body_ok, budget_cfg, env_ok, model_cfg
from .test_grid_header_envelope import full_store
from ._chunk_util import ToyWs, u_doc


def _cfg(tmp_path, name, version, scope="all"):
    d = toy_config_dir(tmp_path / name)
    f = d / "header_b.toml"
    t = f.read_bytes().decode("utf-8")
    t = t.replace('granularity = "pasal"', 'granularity = "ayat"').replace('prompt_version = "v2"', f'prompt_version = "{version}"').replace('scope = "frontier_only"', f'scope = "{scope}"')
    f.write_bytes(t.encode("utf-8"))
    return d


def test_binding_hash_follows_config_prompt_version(tmp_path):
    h = {}
    for v in ("v1", "v2"):
        b = load_header_binding(runs_dir=tmp_path / "r", config_dir=_cfg(tmp_path, v, v))
        h[v] = b.prompt_hash
        assert b.prompt_hash == load_prompt(40, v).prompt_hash
    assert h["v1"] != h["v2"]
    assert load_header_binding(runs_dir=tmp_path / "r").prompt_hash == h["v2"]  # config repo = v2


def test_grid_without_v2_store_reports_header_missing_not_v1(tmp_path):
    doc = u_doc()
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    w = {"doc": doc, "cfg": None, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}
    cfg1, cfg2 = _cfg(tmp_path, "c1", "v1"), _cfg(tmp_path, "c2", "v2")
    w["cfg"] = cfg2
    store = full_store(w)  # header lengkap, lalu ditulis ke direktori hash v1 saja
    p12 = load_prompt(40, "v1").prompt_hash[:12]
    for cid, rec in store.records.items():
        d = tmp_path / "runs" / "headers" / rec["granularity"] / p12
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{cid}.json").write_bytes(json.dumps(rec).encode("utf-8"))
    sp = tmp_path / "runs" / "spark" / "records"
    sp.mkdir(parents=True)
    (sp / "bT.json").write_bytes(json.dumps({"clean_sha256": doc.clean_sha256}).encode("utf-8"))

    def go(cfg):
        return run_family_grid("uupt", doc=doc, tokenizer=ToyWs(), runs_dir=tmp_path / "runs", butir_dir=butir, config_dir=cfg,
                               encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb",
                               headers=load_header_binding(runs_dir=tmp_path / "runs", config_dir=cfg))

    r2 = go(cfg2)
    assert r2.record["failed_settings"] and {f["reason"] for f in r2.record["failed_settings"]} == {"header_missing"}
    r1 = go(cfg1)
    assert r1.record["failed_settings"] == []  # kontrol: store v1 sah untuk v1


def test_w3_forwards_schema_max_length(tmp_path, monkeypatch):
    bodies = []

    def respond(tr, request):
        body = json.loads(request.content.decode("utf-8"))
        bodies.append(body)
        cid = re.search(r"chunk_id: (\S+)", body["input"]).group(1)
        return Resp(200, body_ok({"chunk_id": cid, "header": "Konteks singkat"}))

    tr = FakeTransport(Clock(), default=respond)
    s = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs")
    real = bc.load

    def patched(name, config_dir=None):
        c = real(name, config_dir)
        if name == "header_b":
            c["schema_max_length_chars"] = 190
        return c

    monkeypatch.setattr("backend.header_b.run.config.load", patched)
    app = create_app(s, env=env_ok(), model_config=model_cfg(), budget_config=budget_cfg(), replay=False, spark_transport=tr.transport)
    r = TestClient(app, raise_server_exceptions=False).post("/api/families/uupt/headers/run",
                                                           json={"doc_id": "uupt-40-2007", "granularity": "ayat", "sample": 1})
    assert r.status_code == 200, r.text
    assert bodies
    assert header_schema(190)["properties"]["header"]["maxLength"] == 190
    assert all(re.search(r'"maxLength":\s*190', json.dumps(b)) for b in bodies)  # warm + panggilan unit
