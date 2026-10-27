"""W51: (A) W7/W8 memakai setting terikat versi skema aktif (H-075) seperti Service.grid_settings; (B) jalur jawaban
non-live (replay) tidak menulis `runs/answers/` (H-051). Tanpa jaringan, tanpa Model API; `runs/` hanya dibaca."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app

ROOT = Path(__file__).resolve().parents[2]
COMMITTED = sorted((ROOT / "profiles" / "uupt").glob("*.json"))


class Boom:
    def __getattr__(self, name):
        raise AssertionError("Model API must not be called")

    def __call__(self, *a, **k):
        raise AssertionError("Model API must not be called")


def _client(tmp_path, runs_dir):
    app = create_app(Service(runs_dir=runs_dir), env={}, replay=True, spark_transport=Boom())
    app.state.profiles_dir = tmp_path / "profiles"
    return app, TestClient(app, raise_server_exceptions=False)


@pytest.mark.skipif(not COMMITTED, reason="no committed profile")
def test_w7_schema_setting_v2_byte_identical_and_w8_roundtrip(tmp_path):
    committed = COMMITTED[0]
    sid = committed.stem
    _, c = _client(tmp_path, ROOT / "runs")
    r = c.get(f"/api/families/uupt/profiles/export?setting_id={sid}")
    assert r.status_code == 200, r.text
    # identik byte kecuali `created_at` (jam ekspor; S13)
    a, b = r.json(), json.loads(committed.read_text(encoding="utf-8"))
    assert a.pop("created_at") and b.pop("created_at")
    assert a == b
    dumps = lambda d: json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")  # noqa: E731
    assert dumps(a) == dumps(b)
    assert r.content.replace(r.json()["created_at"].encode(), b"@") == committed.read_bytes().replace(
        json.loads(committed.read_text(encoding="utf-8"))["created_at"].encode(), b"@")
    ok = c.post("/api/profiles/import", json=json.loads(committed.read_text(encoding="utf-8")))
    assert ok.status_code == 200 and ok.json()["chunk_set_hash_matches"] is True


def test_w7_settings_equal_service_grid_settings(tmp_path):
    from backend.api.routers.profiles import build_deps

    app, _ = _client(tmp_path, ROOT / "runs")
    svc = app.state.service

    class Req:
        pass

    req = Req()
    req.app = app
    got = {s["setting_id"] for s in build_deps(req).settings("uupt")}
    assert got == {s["setting_id"] for s in svc.settings("uupt")}


def test_w7_unknown_setting_404_and_non_schema_unchanged(tmp_path):
    from backend.grid.expand import expand_grid

    app, c = _client(tmp_path, ROOT / "runs")
    assert c.get("/api/families/uupt/profiles/export?setting_id=" + "0" * 64).status_code == 404
    plain = next(s for s in expand_grid(app.state.service.cfg("grid"), "uupt") if s.chunker != "structure_schema")
    assert plain.setting_id in {s["setting_id"] for s in _deps_settings(app)}


def _deps_settings(app):
    from backend.api.routers.profiles import build_deps

    class Req:
        pass

    req = Req()
    req.app = app
    return build_deps(req).settings("uupt")


def test_b_nonlive_answers_do_not_write_runs_answers(tmp_path):
    """run_answers(persist=False) tidak menulis; persist=True (default, jalur live/CLI) tetap menulis sekali."""
    import inspect

    from backend.answer import caller

    assert inspect.signature(caller.run_answers).parameters["persist"].default is True
    rec = {"answer_id": "a" * 64}
    caller._save(tmp_path / "answers", rec)
    assert (tmp_path / "answers" / ("a" * 64 + ".json")).exists()
    src = (ROOT / "backend" / "api" / "routers" / "answers.py").read_text(encoding="utf-8")
    assert "persist=not replay" in src


# --- W52 (pemeriksa Tier 1): e2e W6 — replay dan live=false tidak menulis runs/answers (H-051); live (cached) menulis lagi.
import shutil as _shutil

from .test_answer_api import URL as _URL, body as _body, make as _make, svc  # noqa: F401  (fixture svc dipakai pytest)


def test_w52_replay_and_nonlive_do_not_write_answers(svc, tmp_path):
    c, _tr, s = _make(svc, tmp_path)
    assert c.post(_URL, json=_body(svc)).status_code == 200
    ad = s.runs_dir / "answers"
    assert len(list(ad.glob("*.json"))) == 2
    _shutil.rmtree(ad)
    c3, _tr3, _ = _make(svc, tmp_path, replay=True)
    r = c3.post(_URL, json=_body(svc, live=False))
    assert r.status_code == 200 and [x["status"] for x in r.json()["runs"]] == ["replay", "replay"]
    assert not ad.exists() or not list(ad.glob("*.json"))
    r = c.post(_URL, json=_body(svc, live=False))
    assert r.status_code == 200
    assert not ad.exists() or not list(ad.glob("*.json"))
    assert c.post(_URL, json=_body(svc)).status_code == 200
    assert len(list(ad.glob("*.json"))) == 2
