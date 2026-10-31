"""I-69 (G-49): ekspor statis gagal-keras bila ada GET/POST non-200 di luar kelas sah. Klien palsu, tanpa HF, jaringan, atau Model API."""

from __future__ import annotations

import types

import pytest

import backend.replay.export as ex
from backend.api.service import SETTING_UNAVAILABLE_PREFIX

B, S = "b" * 64, "c" * 64


class Resp:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


def err(code, status, message="x"):
    return Resp(status, {"error": {"code": code, "message": message}})


@pytest.fixture
def stub(monkeypatch, tmp_path):
    """Dunia kecil: satu dokumen, satu setting, satu butir, satu profil. `rules` menimpa respons per (metode, ciri url)."""
    snap = {"family": "uupt", "budget_tokens": 2000, "replay": True, "corpus": [{"doc_id": "d1"}], "items": [{"id": "it-1"}],
            "schemas": [{"schema_version": 1}],
            "settings": [{"setting_id": B, "chunker": "structure_handwritten", "header_b": False, "retrieval_mode": "dense"}]}
    st = types.SimpleNamespace(get_rules=[], post_rule=None, snap=snap)

    class FakeClient:
        def __init__(self, app, **kw):
            pass

        def get(self, url, params=None):
            for match, resp in st.get_rules:
                if match(url, params or {}):
                    return resp
            if url == "/api/health":
                return Resp(200, {"status": "ok", "config_hash": "h", "model_profiles": [{"model_profile": "meta", "model": "m", "available": False}]})
            if url.endswith("/snapshot"):
                return Resp(200, snap)
            if "/docs/" in url:
                return Resp(200, {"doc_id": "d1", "text": "t", "chunks": [], "headers": None})
            if url in ("/api/runs", "/api/families"):
                return Resp(200, [{"family": "uupt"}] if url == "/api/families" else [])
            if url.endswith("/proposals"):
                return Resp(200, {"proposals": []})
            return Resp(200, {"ok": True})

        def post(self, url, json=None):
            return st.post_rule(json) if st.post_rule else Resp(200, {"best": {"x": 1}})

    monkeypatch.setattr("starlette.testclient.TestClient", FakeClient)
    monkeypatch.setattr(ex, "baseline_id", lambda app, fam, best: S)
    st.app = types.SimpleNamespace(state=types.SimpleNamespace(replay=True, service=types.SimpleNamespace(
        cfg=lambda n: {"budget": {"default_tokens": 2000, "comparison_tokens": []}})))
    st.lic = tmp_path / "lic"
    st.lic.mkdir()
    st.out = tmp_path / "out"
    monkeypatch.setattr("backend.api.app.create_app", lambda **kw: st.app)
    return st


def run_cli(stub, capsys, *extra):
    # license_root default = repo root; ekspor lewat main memakai default, jadi arahkan ke direktori kosong
    orig = ex.export_static
    ex.export_static = lambda out, app, **kw: orig(out, app, license_root=stub.lic, **kw)
    try:
        code = ex.main(["--out", str(stub.out), *extra])
    finally:
        ex.export_static = orig
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def retrieval_500():
    return (lambda url, p: url.endswith("/retrieval")), err("internal_error", 500, "boom /home/secret/path")


def test_t1_all_200_exit_0(stub, capsys):
    code, out, _ = run_cli(stub, capsys)
    assert code == 0
    assert "failed requests: 0" in out
    assert (stub.out / "data" / "manifest.json").is_file()


def test_t2_retrieval_500_exit_3_nothing_written(stub, capsys):
    stub.get_rules.append(retrieval_500())
    code, out, errout = run_cli(stub, capsys)
    assert code == 3
    assert "retrieval/: 1 (500 x1)" in out and "failed requests: 1" in out
    assert "/home/secret" not in out + errout and "boom" not in out + errout  # pesan galat mentah tidak dicetak
    assert not stub.out.exists()


def test_t2_export_static_raises_and_writes_nothing(stub):
    stub.get_rules.append(retrieval_500())
    (stub.out / "data").mkdir(parents=True)
    (stub.out / "data" / "old.json").write_text("{}")
    with pytest.raises(ex.ExportIncomplete) as ei:
        ex.export_static(stub.out, stub.app, license_root=stub.lic)
    assert [m.kind for m in ei.value.failed] == ["retrieval/"]
    assert (stub.out / "data" / "old.json").is_file() and not (stub.out / "data" / "manifest.json").exists()


def test_t3_s2_setting_unavailable_422_is_skipped_exit_0(stub, capsys):
    stub.get_rules.append((lambda url, p: "/docs/" in url and "setting_id" in p,
                           err("validation_failed", 422, f"{SETTING_UNAVAILABLE_PREFIX}: header B.")))
    code, out, _ = run_cli(stub, capsys)
    assert code == 0 and "failed requests: 0" in out
    assert "skipped by design: docs/ (setting chunks) 422 setting_unavailable x1" in out


def test_t3_s1_no_stored_run_409_is_skipped_exit_0(stub, capsys):
    stub.post_rule = lambda body: err("replay_no_stored_run", 409, "no stored run")
    code, out, _ = run_cli(stub, capsys)
    assert code == 0 and "failed requests: 0" in out
    assert "skipped by design: answers/ 409 replay_no_stored_run x1" in out


def test_t3_skipped_counts_in_info(stub):
    stub.post_rule = lambda body: err("replay_no_stored_run", 409)
    info = ex.export_static(stub.out, stub.app, license_root=stub.lic)
    assert info["failed"] == 0 and info["skipped"] == {"answers/ 409 replay_no_stored_run": 1}


@pytest.mark.parametrize("match, resp, n", [
    (lambda url, p: "/docs/" in url and "setting_id" in p, err("validation_failed", 422, "Chunk offsets do not match."), 1),
    (lambda url, p: "/docs/" in url and "schema_version" in p, err("validation_failed", 422, "Schema chunking failed."), 2),  # skema dicoba untuk uupt dan akta
    (lambda url, p: "/docs/" in url and "schema_version" in p, err("not_found", 404), 2),
    (lambda url, p: "/docs/" in url and "setting_id" in p, err("internal_error", 500), 1),
], ids=["docs-422-other-message", "schema-422", "schema-404", "docs-500"])
def test_t3b_other_422_and_schema_failures_fail(stub, capsys, match, resp, n):
    stub.get_rules.append((match, resp))
    code, out, _ = run_cli(stub, capsys)
    assert code == 3 and "docs/" in out and f"failed requests: {n}" in out
    assert not stub.out.exists()


def test_t3b_post_409_other_code_fails(stub, capsys):
    stub.post_rule = lambda body: err("conflict", 409)
    code, out, _ = run_cli(stub, capsys)
    assert code == 3 and "answers/: 1 (409 x1)" in out


def test_t4_allow_missing_writes_and_warns(stub, capsys):
    stub.get_rules.append(retrieval_500())
    code, out, _ = run_cli(stub, capsys, "--allow-missing")
    assert code == 0
    assert "WARNING" in out and "retrieval/" in out
    assert (stub.out / "data" / "manifest.json").is_file()
    info = ex.export_static(stub.out, stub.app, license_root=stub.lic, allow_missing=True)
    assert info["failed"] == 1
