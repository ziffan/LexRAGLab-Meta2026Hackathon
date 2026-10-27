"""M2.5 W6 (profil berperan C vs bukan), R1 health, dan CLI pembanding. Transport palsu; korpus nyata, tanpa encoder."""

import json

from fastapi.testclient import TestClient

from backend.answer import compare_c
from backend.api.app import Service, create_app
from backend.spark import store

from .m25_fakes import chat_body, env_m25, m25_model_cfg
from .spark_fakes import Clock, FakeTransport, Resp, body_ok, budget_cfg
from .test_answer_api import ITEM, JAWAB, URL, body, ids, svc  # noqa: F401  (svc = fixture modul)


def make(svc, tmp_path, *, probe=None, replay=False, default=None):
    tr = FakeTransport(Clock(), None, default if default is not None else Resp(200, body_ok(JAWAB)))
    s = Service(tokenizer=svc.tokenizer, runs_dir=tmp_path / "runs", encoder=svc._encoder, embed_cache_dir=svc.embed_cache_dir)
    s._docs, s._pipeline = svc._docs, svc._pipeline
    app = create_app(s, env=env_m25(), model_config=m25_model_cfg(), budget_config=budget_cfg(), replay=replay,
                     spark_transport=tr.transport)
    app.state.local_probe = probe or (lambda url, model: (True, "Available."))
    return TestClient(app, raise_server_exceptions=False), tr, s


def test_w6_non_c_profile_still_422_and_c_profiles_accepted(svc, tmp_path):
    c, tr, _ = make(svc, tmp_path)
    r = c.post(URL, json=body(svc, model_profile="b_only"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_failed" and tr.calls == 0
    r = c.post(URL, json=body(svc, model_profile="baseten_open"))
    assert r.status_code == 200, r.text
    assert tr.requests[0]["path"].endswith("/responses") and tr.requests[0]["body"]["text"]["format"]["strict"] is True
    assert {a["model_profile"] for a in (r.json()["best"], r.json()["baseline"])} == {"baseten_open"}
    assert all(x["provider"] == "baseten" and x["model"] == "meta-models/muse-spark-open-1026" for x in r.json()["runs"])


def test_w6_glimmer_live_records_model_quant_effort_and_stays_separate(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, default=Resp(200, chat_body(JAWAB)))
    # Contributor dulu (Responses), lalu Glimmer (Chat Completions): dua kumpulan jawaban, tidak digabung.
    tr.script = [Resp(200, body_ok(JAWAB)), Resp(200, body_ok(JAWAB))]
    rm = c.post(URL, json=body(svc, model_profile="meta"))
    rg = c.post(URL, json=body(svc, model_profile="glimmer_local"))
    assert rm.status_code == 200 and rg.status_code == 200, rg.text
    for slot in ("best", "baseline"):
        assert rg.json()[slot]["model_profile"] == "glimmer_local" and rm.json()[slot]["model_profile"] == "meta"
        assert rg.json()[slot]["answer_id"] != rm.json()[slot]["answer_id"]
    for run in rg.json()["runs"]:
        assert (run["provider"], run["model"], run["quantization"], run["effort"], run["cost_usd_micros"]) == (
            "lmstudio_local", "meta/muse-glimmer", "Q4_K_M", "high", 0)
    assert [x["provider"] for x in rm.json()["runs"]] == ["meta", "meta"]
    assert {t["model_profile"] for t in rg.json()["summary"]} == {"glimmer_local"}
    files = list((s.runs_dir / "answers").glob("*.json"))
    assert sorted(json.loads(f.read_text(encoding="utf-8"))["model_profile"] for f in files) == ["glimmer_local"] * 2 + ["meta"] * 2


def test_w6_glimmer_server_down_is_503_before_any_call(svc, tmp_path):
    c, tr, _ = make(svc, tmp_path, probe=lambda u, m: (False, "Local model server is not running. Start it in LM Studio to enable this model."))
    r = c.post(URL, json=body(svc, model_profile="glimmer_local"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    assert "not running" in r.json()["error"]["message"] and tr.calls == 0


def test_w6_glimmer_stored_run_replays_when_server_down(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, default=Resp(200, chat_body(JAWAB)))
    assert c.post(URL, json=body(svc, model_profile="glimmer_local")).status_code == 200
    n = tr.calls
    c.app.state.local_probe = lambda u, m: (False, "down")
    r = c.post(URL, json=body(svc, model_profile="glimmer_local", live=False))  # hasil tersimpan tetap tampil
    assert r.status_code == 200 and tr.calls == n and r.json()["best"]["model_profile"] == "glimmer_local"


def test_health_profiles_label_quant_effort_availability(svc, tmp_path):
    c, _, _ = make(svc, tmp_path, probe=lambda u, m: (False, "Local model server is not running."))
    rows = {p["model_profile"]: p for p in c.get("/api/health").json()["model_profiles"]}
    g = rows["glimmer_local"]
    assert g["available"] is False and g["local"] is True and g["quantization"] == "Q4_K_M" and g["effort"] == "high"
    assert g["label"] == "Glimmer (local)" and g["roles"] == ["c"] and "not running" in g["unavailable_reason"]
    assert rows["baseten_open"]["available"] is True and rows["baseten_open"]["roles"] == ["c"]
    assert rows["meta"]["available"] is True and rows["meta"]["unavailable_reason"] is None and rows["meta"]["local"] is False
    text = json.dumps(c.get("/api/health").json())
    assert "127.0.0.1" not in text and "fake-baseten" not in text and "BT7Q2M9" not in text


def test_health_replay_does_not_probe(svc, tmp_path):
    calls = []
    c, _, _ = make(svc, tmp_path, replay=True, probe=lambda u, m: calls.append(1) or (False, "x"))
    rows = {p["model_profile"]: p for p in c.get("/api/health").json()["model_profiles"]}
    assert rows["glimmer_local"]["available"] is True and not calls


# --- CLI -----------------------------------------------------------------------------------------------------

def _seed_contributor(svc, tmp_path):
    c, tr, s = make(svc, tmp_path)
    assert c.post(URL, json=body(svc, model_profile="meta")).status_code == 200
    return s


def _cli(s, argv, tr, probe=lambda u, m: (True, "ok"), out=None):
    lines = [] if out is None else out
    rc = compare_c.main(argv, service=s, env=env_m25(), model_config=m25_model_cfg(), budget_config=budget_cfg(),
                        runs_dir=s.runs_dir, transport=tr.transport, out=lines.append, probe=probe)
    return rc, lines


def test_cli_project_only_makes_no_call_and_writes_nothing(svc, tmp_path):
    s = _seed_contributor(svc, tmp_path)
    before = sorted(p.name for p in (s.runs_dir).rglob("*.json"))
    tr = FakeTransport(Clock(), None, Resp(500, {}))
    rc, lines = _cli(s, ["--model-profile", "baseten_open", "--items", ITEM, "--project-only"], tr)
    assert rc == 0 and tr.calls == 0 and sorted(p.name for p in s.runs_dir.rglob("*.json")) == before
    assert any(f"{ITEM}: calls=2" in ln for ln in lines)
    total = next(ln for ln in lines if ln.startswith("total projected"))
    assert "micro-USD=0 " not in total and "baseten_open" in total  # Baseten berbiaya > 0
    rc, lines = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM, "--project-only"], tr)
    assert rc == 0 and tr.calls == 0 and any("[local, cost 0]" in ln for ln in lines)
    assert any("quantization=Q4_K_M effort=high" in ln for ln in lines)


def test_cli_reuses_contributor_context_exactly_and_caches(svc, tmp_path):
    s = _seed_contributor(svc, tmp_path)
    src = {json.loads(p.read_text(encoding="utf-8"))["slot"]: json.loads(p.read_text(encoding="utf-8"))
           for p in (s.runs_dir / "answers").glob("*.json")}
    tr = FakeTransport(Clock(), None, Resp(200, chat_body(JAWAB)))
    rc, lines = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM], tr)
    assert rc == 0 and tr.calls == 2, lines
    new = [json.loads(p.read_text(encoding="utf-8")) for p in (s.runs_dir / "answers").glob("*.json")]
    g = {a["slot"]: a for a in new if a["model_profile"] == "glimmer_local"}
    assert set(g) == {"best", "baseline"}
    for slot in ("best", "baseline"):  # konteks persis: chunk_ids sama dengan jawaban Contributor
        assert g[slot]["context_chunk_ids"] == src[slot]["context_chunk_ids"] and g[slot]["setting_id"] == src[slot]["setting_id"]
        assert g[slot]["answer_id"] != src[slot]["answer_id"]
    assert [r["messages"][0]["content"] for r in (tr.requests[0]["body"], tr.requests[1]["body"])]
    recs = [r for r in store.load_records(s.runs_dir) if r.provider == "lmstudio_local"]
    assert len(recs) == 2 and all(r.prompt_version == "v2" for r in recs)
    rc, _ = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM], tr)  # run ulang: cache
    assert rc == 0 and tr.calls == 2


def test_cli_glimmer_server_down_aborts_without_call(svc, tmp_path):
    s = _seed_contributor(svc, tmp_path)
    tr = FakeTransport(Clock(), None, Resp(200, chat_body(JAWAB)))
    rc, _ = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM], tr, probe=lambda u, m: (False, "down"))
    assert rc == 3 and tr.calls == 0


def test_cli_rejects_non_c_or_unknown_profile_and_same_source(svc, tmp_path):
    s = _seed_contributor(svc, tmp_path)
    tr = FakeTransport(Clock())
    for prof in ("b_only", "nama-ngawur", "meta"):
        rc, _ = _cli(s, ["--model-profile", prof, "--items", ITEM], tr)
        assert rc == 2 and tr.calls == 0


def test_cli_stops_without_calling_when_context_hash_mismatches(svc, tmp_path):
    s = _seed_contributor(svc, tmp_path)
    for f in (s.runs_dir / "spark" / "records").glob("*.json"):  # rusak-kan cache_key sumber: masukan tak bisa dibuktikan identik
        d = json.loads(f.read_text(encoding="utf-8"))
        d["cache_key"] = "0" * 64
        f.write_text(json.dumps(d), encoding="utf-8")
    tr = FakeTransport(Clock(), None, Resp(200, chat_body(JAWAB)))
    lines = []
    rc, lines = _cli(s, ["--model-profile", "glimmer_local", "--items", ITEM], tr)
    assert rc == 2 and tr.calls == 0
    assert any("does not match the source run hash" in ln for ln in lines)
    assert not [r for r in store.load_records(s.runs_dir) if r.provider == "lmstudio_local"]


def test_w6_live_via_cli_profile_is_409_but_stored_results_still_read(svc, tmp_path):
    c, tr, s = make(svc, tmp_path, default=Resp(200, chat_body(JAWAB)))
    c.app.state.model_config["profiles"]["glimmer_local"]["live_via_cli"] = True
    r = c.post(URL, json=body(svc, model_profile="glimmer_local"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "live_unavailable" and tr.calls == 0
    assert "CLI" in r.json()["error"]["message"]
    r = c.post(URL, json=body(svc, model_profile="glimmer_local", live=False))
    assert r.json()["error"]["code"] == "replay_no_stored_run"  # bukan live_unavailable: jalur baca tetap
    row = next(p for p in c.get("/api/health").json()["model_profiles"] if p["model_profile"] == "glimmer_local")
    assert row["live_via_cli"] is True
