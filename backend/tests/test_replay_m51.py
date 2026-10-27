"""M5.1: X-Replay di semua respons, penolakan tulis di replay, ekspor statis dari fixture kecil, dan pemeriksa isi snapshot.

Tanpa jaringan dan tanpa Model API. Korpus dan butir nyata, encoder palsu, `runs/` kosong di tmp. Key dan host palsu dari spark_fakes."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.replay.export import ExportError, build_files, export_static, main as export_main, sid
from backend.replay.scan import SnapshotLeak, scan_dir, scan_files, scan_text
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder
from .spark_fakes import BASE, K, budget_cfg, model_cfg

FAKE_KEY = "sk-" + "FAKEFAKEFAKE0123456789abcdef"  # dibentuk dari potongan agar literal kunci tidak ada di berkas terlacak (konvensi S12)


def make_app(root, *, replay: bool, env=None):
    svc = Service(tokenizer=get_tokenizer(), runs_dir=root / "runs", encoder=FakeEncoder(), embed_cache_dir=root / "emb")
    return create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE} if env is None else env,
                      model_config=model_cfg(), budget_config=budget_cfg(), replay=replay)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("m51")
    app = make_app(root, replay=True)
    files = build_files(app, families=("uupt", "akta"), retrieval=True, answers=True)
    return {"root": root, "app": app, "files": files}


# ---- X-Replay di semua respons ----
@pytest.mark.parametrize("replay", [True, False])
def test_x_replay_header_on_every_response(tmp_path, replay):
    c = TestClient(make_app(tmp_path, replay=replay), raise_server_exceptions=False)
    want = "true" if replay else "false"
    for r in (c.get("/api/health"), c.get("/api/runs"), c.get("/api/families/uupt/snapshot"), c.get("/api/does-not-exist"),
              c.get("/api/runs", params={"kind": "bogus"}), c.get("/api/families/xyz/snapshot"), c.get("/api/families/uupt/proposals"),
              c.post("/api/profiles/import", json={})):
        assert r.headers.get("x-replay") == want, (r.request.url, r.status_code)


def test_x_replay_header_on_unhandled_500(tmp_path):
    app = make_app(tmp_path, replay=True)

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("x")

    r = TestClient(app, raise_server_exceptions=False).get("/api/boom")
    assert r.status_code == 500 and r.headers["x-replay"] == "true"
    assert r.json() == {"error": {"code": "internal_error", "message": "Unexpected server error."}}


# ---- penolakan tulis di replay ----
def test_w5_decision_rejected_in_replay_but_not_live(tmp_path):
    body = {"decision": "ditolak", "edited": None, "operator_note": None}
    rep = TestClient(make_app(tmp_path / "a", replay=True), raise_server_exceptions=False).post("/api/proposals/p-1/decision", json=body)
    assert rep.status_code == 400 and rep.json()["error"]["code"] == "invalid_request" and rep.headers["x-replay"] == "true"
    live = TestClient(make_app(tmp_path / "b", replay=False), raise_server_exceptions=False).post("/api/proposals/p-1/decision", json=body)
    assert live.status_code == 404 and live.json()["error"]["code"] == "not_found"  # lolos middleware: usulan tak dikenal


def test_replay_write_endpoints_do_not_call_the_model_or_write(tmp_path):
    c = TestClient(make_app(tmp_path, replay=True, env={}), raise_server_exceptions=False)
    r = c.post("/api/families/uupt/grid/run", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "replay_no_stored_run"
    r = c.post("/api/families/uupt/schemas/1/correct", json={"schema": {}, "operator_note": None})
    assert r.status_code == 400 and r.headers["x-replay"] == "true"
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").rglob("*.json"))


# ---- ekspor: berkas yang diharapkan ----
def test_export_requires_a_replay_app(tmp_path):
    with pytest.raises(ExportError):
        build_files(make_app(tmp_path, replay=False))


def test_export_writes_expected_files(world):
    f = world["files"]
    for rel in ("health.json", "runs.json", "manifest.json", "snapshot/uupt/default.json", "snapshot/akta/default.json", "proposals/uupt.json"):
        assert rel in f, rel
    snap = json.loads(f["snapshot/uupt/default.json"])
    assert snap["replay"] is True and snap["family"] == "uupt" and f"snapshot/uupt/{snap['budget_tokens']}.json" in f
    cfg = world["app"].state.service.cfg("grid")["budget"]
    for b in cfg.get("comparison_tokens", []):
        assert f"snapshot/uupt/{b}.json" in f
    doc_id = snap["corpus"][0]["doc_id"]
    text = json.loads(f[f"docs/uupt/{doc_id}/_text.json"])
    assert text["chunks"] is None and len(text["text"]) > 1000
    s0 = next(s for s in snap["settings"] if f"docs/uupt/{doc_id}/{sid(s['setting_id'])}.json" in f)
    part = json.loads(f[f"docs/uupt/{doc_id}/{sid(s0['setting_id'])}.json"])
    assert set(part) == {"doc_id", "chunks", "headers"} and part["chunks"]  # teks tidak diulang per setting
    item = snap["items"][0]["id"]
    ret = json.loads(f[f"retrieval/uupt/{sid(s0['setting_id'])}/{item}.json"])
    assert set(ret) >= {"retrieved_chunk_ids", "ranks", "scores", "packed_tokens"}
    assert all(len(k) < 150 for k in f)  # jalur pendek (MAX_PATH Windows)


def test_export_matches_the_live_api_response(world):
    snap = TestClient(world["app"]).get("/api/families/uupt/snapshot").json()
    assert json.loads(world["files"]["snapshot/uupt/default.json"]) == snap


def test_static_health_lists_only_profiles_with_stored_answers(world):
    h = json.loads(world["files"]["health.json"])
    assert h["replay"] is True and h["static"] is True
    assert h["model_profiles"] == []  # tidak ada run tersimpan di fixture: profil dev tidak diekspos
    assert not [k for k in world["files"] if k.startswith("answers/")]


def test_manifest_hashes_match_files(world):
    m = json.loads(world["files"]["manifest.json"])
    assert m["static"] is True and "manifest.json" not in m["files"]
    for rel, h in m["files"].items():
        assert hashlib.sha256(world["files"][rel]).hexdigest() == h


def test_export_static_writes_to_disk_and_replaces_old_data(world, tmp_path):
    out = tmp_path / "dist-static"
    (out / "data").mkdir(parents=True)
    (out / "data" / "stale.json").write_text("{}", encoding="utf-8")
    info = export_static(out, world["app"], secrets=[K], base_urls=[BASE], retrieval=False, answers=False)
    assert (out / "data" / "health.json").is_file() and not (out / "data" / "stale.json").exists()
    assert info["n_files"] == len(list((out / "data").rglob("*.json")))
    assert scan_dir(out / "data", secrets=[K], base_urls=[BASE]) == []
    assert b"\r" not in (out / "data" / "health.json").read_bytes()


def test_export_clean_of_env_key_and_host(world):
    blob = b"".join(world["files"].values()).decode("utf-8")
    assert K not in blob and BASE not in blob and "fake-host.invalid" not in blob
    assert scan_files(world["files"], secrets=[K], base_urls=[BASE]) == []


# ---- pemeriksa isi ----
def test_scan_rejects_fake_key_value_prefix_and_pattern():
    assert [f.kind for f in scan_text(f'{{"x":"{FAKE_KEY}"}}', secrets=[FAKE_KEY])][:1] == ["secret_value"]
    assert scan_text("prefix sk-FAKEFAKEFAK tail", secrets=[FAKE_KEY])  # awalan 12 karakter
    assert any(f.kind == "api_key_pattern" for f in scan_text(f"a {FAKE_KEY} b"))
    assert any(f.kind == "bearer_token" for f in scan_text("Authorization: Bearer " + "abcdefghijklmnop12345"))


def test_scan_rejects_local_paths_and_hosts():
    for text in ("D:\\\\WORKDIR\\\\x", "C:\\Data\\me\\a", "see /home/user/runs", "/Users/bob/x", "http://127.0.0.1:8000/api", "https://api.example.com/v1", "localhost:5173"):
        assert scan_text(text), text
    assert any(f.kind == "base_url_value" for f in scan_text("u https://fake-host.invalid/v1/ x", base_urls=[BASE]))


def test_scan_allows_normal_legal_text():
    text = "Pasal 1 ayat (2): Perseroan Terbatas, yang selanjutnya disebut Perseroan, adalah badan hukum. a:b dan/atau c/d; UU No. 40 Tahun 2007."
    assert scan_text(text) == []


def test_scan_findings_never_echo_the_secret():
    fs = scan_text(f"{FAKE_KEY} D:\\\\WORKDIR", "f.json", secrets=[FAKE_KEY])
    assert fs and all(FAKE_KEY not in str(f) and "WORKDIR" not in str(f) for f in fs)
    assert FAKE_KEY not in str(SnapshotLeak(fs))


def test_export_refuses_and_writes_nothing_when_content_leaks(world, tmp_path):
    out = tmp_path / "leaky"
    leak = "Perseroan Terbatas"  # ada di teks UU yang diekspor: berperan sebagai 'key' yang bocor
    with pytest.raises(SnapshotLeak) as ei:
        export_static(out, world["app"], secrets=[leak], retrieval=False, answers=False)
    assert ei.value.findings and not out.exists()


def test_scan_dir_flags_planted_files(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "ok.json").write_text('{"a":1}', encoding="utf-8")
    (d / "bad.json").write_text(json.dumps({"p": "C:\\Data\\x\\y", "k": FAKE_KEY}), encoding="utf-8")
    kinds = {(f.path, f.kind) for f in scan_dir(d)}
    assert ("bad.json", "local_path_windows") in kinds and ("bad.json", "api_key_pattern") in kinds
    assert not [f for f in scan_dir(d) if f.path == "ok.json"]


def test_cli_check_exit_codes(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.json").write_text('{"a":1}', encoding="utf-8")
    assert export_main(["--check", str(tmp_path)]) == 0
    (tmp_path / "data" / "b.json").write_text('{"p":"D:\\\\WORKDIR"}', encoding="utf-8")
    assert export_main(["--check", str(tmp_path)]) == 1
    assert "WORKDIR" not in capsys.readouterr().out


# ---- jalur W6 tersimpan (klien palsu: tanpa pipeline berat) ----
def test_export_answers_layout_and_profile_availability(monkeypatch):
    import types

    import backend.replay.export as ex

    B, S = "b" * 64, "c" * 64
    snap = {"family": "uupt", "budget_tokens": 2000, "replay": True, "corpus": [], "items": [{"id": "it-1"}],
            "settings": [{"setting_id": B, "chunker": "structure_handwritten", "header_b": False, "retrieval_mode": "dense"}]}
    posted: list[dict] = []

    class Resp:
        def __init__(self, code, data):
            self.status_code, self._d = code, data

        def json(self):
            return self._d

    class FakeClient:
        def __init__(self, app, **kw):
            pass

        def get(self, url, params=None):
            if url == "/api/health":
                return Resp(200, {"status": "ok", "config_hash": "h", "model_profiles": [
                    {"model_profile": "meta", "model": "m", "available": False}, {"model_profile": "glim", "model": "g", "available": False}]})
            if url.endswith("/snapshot"):
                return Resp(200, snap)
            if url.endswith("/docs/d1") or url == "/api/runs":
                return Resp(404, {})
            return Resp(200, {} if "proposals" not in url else {"proposals": []})

        def post(self, url, json=None):
            posted.append(json)
            return Resp(200, {"best": {"x": 1}}) if json["model_profile"] == "meta" else Resp(409, {})

    monkeypatch.setattr("starlette.testclient.TestClient", FakeClient)
    monkeypatch.setattr(ex, "baseline_id", lambda app, fam, best: S)
    # settings dipakai hanya bila ada dokumen; paksa satu dokumen agar B dianggap tersedia
    snap["corpus"] = [{"doc_id": "d1"}]
    orig_get = FakeClient.get
    FakeClient.get = lambda self, url, params=None: (Resp(200, {"doc_id": "d1", "text": "t", "chunks": [], "headers": None})
                                                      if "/docs/d1" in url else orig_get(self, url, params))
    app = types.SimpleNamespace(state=types.SimpleNamespace(replay=True, service=types.SimpleNamespace(
        cfg=lambda n: {"budget": {"default_tokens": 2000, "comparison_tokens": []}})))
    files = ex.build_files(app, families=("uupt",), retrieval=False, answers=True)
    key = f"answers/uupt/it-1/{B[:16]}/{S[:16]}/meta.json"
    assert key in files and not [k for k in files if k.startswith("answers/") and k != key]
    assert posted and all(p["live"] is False for p in posted)
    h = json.loads(files["health.json"])
    assert {p["model_profile"]: p["available"] for p in h["model_profiles"]} == {"meta": True}  # glim tanpa jawaban tersimpan: tidak dicantumkan


def test_static_health_carries_run_cost(tmp_path):
    from .spark_fakes import synth

    app = make_app(tmp_path, replay=True)
    synth(tmp_path / "runs", "a", "meta", 1234, run_id="rc-1")
    synth(tmp_path / "runs", "a", "meta", None, run_id="rc-2")
    synth(tmp_path / "runs", "a", "meta", 66, run_id="rc-3")
    h = json.loads(build_files(app, families=("uupt",), retrieval=False, answers=False)["health.json"])
    assert h["run_cost_usd_micros"] == 1300 and type(h["run_cost_usd_micros"]) is int


# ---- W12: determinisme ekspor ----
def test_export_is_byte_deterministic_with_injected_clock(world):
    from datetime import datetime, timezone

    now = datetime(2026, 10, 27, 10, 0, 0, tzinfo=timezone.utc)
    a = build_files(world["app"], families=("uupt",), retrieval=False, answers=False, now=now)
    b = build_files(world["app"], families=("uupt",), retrieval=False, answers=False, now=now)
    assert a == b and list(a) == list(b)
    m = json.loads(a["manifest.json"])
    assert m["generated_at"] == "2026-10-27T10:00:00Z"
    assert list(m["files"]) == sorted(m["files"])
    raw = a["manifest.json"].decode("utf-8")
    assert raw.index('"config_hash"') < raw.index('"files"') < raw.index('"generated_at"') < raw.index('"static"')  # sort_keys
    assert all(blob.endswith(b"\n") and b"\r" not in blob for blob in a.values())
    for blob in a.values():
        obj = json.loads(blob)
        assert blob == (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def test_source_date_epoch_fixes_generated_at():
    from backend.replay.export import source_date

    assert source_date({}) is None and source_date({"SOURCE_DATE_EPOCH": "abc"}) is None
    assert source_date({"SOURCE_DATE_EPOCH": "1793095200"}).strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-10-27T10:00:00Z"


# ---- W12: env_secrets dan CLI --check dengan env palsu ----
def test_env_secrets_classifies_names_and_skips_short_values():
    from backend.replay.scan import env_secrets

    keys, urls = env_secrets({
        "MUSE_API_KEY": FAKE_KEY, "OPENROUTER_API_KEY": '"' + FAKE_KEY + 'ZZ"', "SHORT_KEY": "abc",
        "MUSE_BASE_URL": "http://gateway.invalid:9", "OTHER_URL": "http://other.invalid", "PATH": "C:\\bin;C:\\x", "NOTE": "nilai-biasa-panjang"})
    assert FAKE_KEY in keys and FAKE_KEY + "ZZ" in keys and "abc" not in keys and len(keys) == 2
    assert urls == ["http://gateway.invalid:9", "http://other.invalid"]
    assert env_secrets({}) == ([], [])


def test_cli_check_uses_process_env_key_and_url(tmp_path, monkeypatch, capsys):
    secret = "zq" + "Xv" * 9  # tanpa pola sk-: hanya terdeteksi lewat nilai dari lingkungan proses
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.json").write_text(json.dumps({"x": "prefix " + secret + " suffix"}), encoding="utf-8")
    monkeypatch.delenv("FAKE_W12_KEY", raising=False)
    assert export_main(["--check", str(tmp_path)]) == 0  # env tanpa rahasia: bersih
    monkeypatch.setenv("FAKE_W12_KEY", secret)
    assert export_main(["--check", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "secret_value" in out and secret not in out
    monkeypatch.delenv("FAKE_W12_KEY")
    (d / "a.json").write_text('{"u":"gateway-w12.invalid/v1"}', encoding="utf-8")
    assert export_main(["--check", str(tmp_path)]) == 0
    monkeypatch.setenv("FAKE_W12_BASE_URL", "gateway-w12.invalid/v1")
    assert export_main(["--check", str(tmp_path)]) == 1
    assert "base_url_value" in capsys.readouterr().out


def test_cli_export_passes_source_date_epoch_as_clock(monkeypatch, tmp_path):
    import backend.api.app as appmod
    import backend.replay.export as ex

    seen = {}
    monkeypatch.setattr(appmod, "create_app", lambda **kw: object())
    monkeypatch.setattr(ex, "export_static", lambda out, app, **kw: seen.update(kw) or {"n_files": 0, "bytes": 0, "data_dir": str(out)})
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1793095200")
    assert export_main(["--out", str(tmp_path)]) == 0
    assert seen["now"].strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-10-27T10:00:00Z"
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert export_main(["--out", str(tmp_path)]) == 0 and seen["now"] is None
