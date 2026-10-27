"""U2 dua deret (M3.2): payload R3 `grid` membawa `header_b` per titik, `failed_settings`, `header_scope`; Service memakai
binding header bila store ada. Tanpa jaringan, tanpa Spark, tanpa menjalankan grid."""

from __future__ import annotations

import json
from types import SimpleNamespace

from backend.api.routers.snapshot import grid_view
from backend.api.service import Service
from backend.grid.headers import DirHeaderStore
from backend.pipeline.grid_run import RunFileStore, load_header_binding


def _pt(sid, split, budget=2000, **kw):
    return {"setting_id": sid, "split": split, "budget_tokens": budget, "mean_span_recall": 0.5, **kw}


def _env(failed=None, with_label=True):
    pts = []
    for sid, hb in (("off1", False), ("on1", True)):
        for sp in ("tune", "held_out"):
            p = _pt(sid, sp)
            if with_label:
                p["header_b"] = hb
            pts.append(p)
    pts.append(_pt("off-big", "tune", budget=4000, header_b=False))
    return {"key": "K", "record": {"failed_settings": failed or []}, "settings_run":
            [{"setting_id": "off1", "budget_tokens": 2000, "header_b": False}, {"setting_id": "on1", "budget_tokens": 2000, "header_b": True},
             {"setting_id": "off-big", "budget_tokens": 4000, "header_b": False}],
            "points": pts, "frontiers": [], "selections": {}, "quality_comparison": [], "skipped": [], "metrics": [], "quality": []}


def test_points_carry_header_series_label():
    grid, _m, _q = grid_view(_env(), 2000, header_scope="frontier_only")
    assert {p["setting_id"]: p["header_b"] for p in grid["held_out"]["points"]} == {"off1": False, "on1": True}
    assert [p["setting_id"] for p in grid["tune"]["points"]] == ["off1", "on1"]  # anggaran lain tidak ikut
    assert grid["header_scope"] == "frontier_only"


def test_label_derived_from_settings_run_when_point_has_none():
    grid, _m, _q = grid_view(_env(with_label=False), 2000)
    assert {p["setting_id"]: p["header_b"] for p in grid["tune"]["points"]} == {"off1": False, "on1": True}


def test_failed_settings_passed_with_reason_and_filtered_by_budget():
    failed = [{"setting_id": "f2000", "reason": "header_missing", "chunk_id": "c1"},
              {"setting_id": "f4000", "reason": "header_stale", "chunk_id": None}]
    settings = [{"setting_id": "f2000", "budget_tokens": 2000}, {"setting_id": "f4000", "budget_tokens": 4000}]
    grid, _m, _q = grid_view(_env(failed), 2000, settings, "all")
    assert grid["failed_settings"] == [{"setting_id": "f2000", "reason": "header_missing", "chunk_id": "c1"}]
    assert grid["header_scope"] == "all"


def test_no_header_points_no_failures_means_no_scope_and_empty_failed():
    env = _env()
    env["points"] = [p for p in env["points"] if not p["header_b"]]
    env["settings_run"] = [s for s in env["settings_run"] if not s["header_b"]]
    grid, _m, _q = grid_view(env, 2000, header_scope="frontier_only")
    assert grid["failed_settings"] == [] and grid["header_scope"] is None


def test_old_record_without_failed_settings_key():
    env = _env()
    env["record"] = {}
    grid, _m, _q = grid_view(env, 2000)
    assert grid["failed_settings"] == []


def test_header_binding_only_when_store_has_headers(tmp_path):
    svc = Service(runs_dir=tmp_path)
    assert svc.header_binding() is None  # tanpa runs/headers
    (tmp_path / "headers" / "pasal").mkdir(parents=True)
    assert svc.header_binding() is None  # dir ada, tanpa berkas untuk prompt_hash saat ini
    prompt12 = load_header_binding(runs_dir=tmp_path).prompt_hash[:12]
    d = tmp_path / "headers" / "pasal" / prompt12
    d.mkdir()
    (d / "c1.json").write_text(json.dumps({"chunk_id": "c1", "header": "H"}), encoding="utf-8", newline="\n")
    hb = svc.header_binding()
    assert hb is not None and isinstance(hb.store, DirHeaderStore)


def test_stored_grid_prefers_header_run_then_falls_back(tmp_path, monkeypatch):
    svc = Service(runs_dir=tmp_path)
    seen = []

    def fake_plan(family, *, create_split=False, headers=None):
        seen.append(headers is not None)
        return SimpleNamespace(key="HKEY" if headers is not None else "PKEY", split=None)

    monkeypatch.setattr(svc, "plan", fake_plan)
    store = RunFileStore(tmp_path / "grid")
    store.write("PKEY", {"key": "PKEY", "record": {"x": 1}})
    assert svc.stored_grid("uupt")[1]["key"] == "PKEY" and seen == [False]  # tanpa store header
    prompt12 = load_header_binding(runs_dir=tmp_path).prompt_hash[:12]
    d = tmp_path / "headers" / "pasal" / prompt12
    d.mkdir(parents=True)
    (d / "c1.json").write_text("{}", encoding="utf-8", newline="\n")
    seen.clear()
    assert svc.stored_grid("uupt")[1]["key"] == "PKEY" and seen == [True, False]  # run header belum ada: jatuh ke run biasa
    store.write("HKEY", {"key": "HKEY", "record": {"failed_settings": []}})
    seen.clear()
    assert svc.stored_grid("uupt")[1]["key"] == "HKEY" and seen == [True]


# --- jalur 422 HeaderError dan penyempitan except di header_binding (W7) ---
import logging

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.errors import ApiError
from backend.config import ConfigError
from backend.grid.headers import HeaderMissingError
from backend.pipeline.grid_run import GridRunError
from backend.pipeline.pipeline import SettingNotAvailable
from backend.tokenizer import get_tokenizer

from .spark_fakes import BASE, K, budget_cfg, model_cfg

FAM = "/api/families/uupt"


class _Raising:
    def __init__(self, exc):
        self.exc = exc

    def retrieve(self, s, item):
        raise self.exc


def _retrieval_client(tmp_path, monkeypatch, exc):
    svc = Service(tokenizer=get_tokenizer(), runs_dir=tmp_path / "runs")
    monkeypatch.setattr(svc, "find_setting", lambda family, sid: object())
    monkeypatch.setattr(svc, "items", lambda family: [{"id": "i1", "family": "uupt", "origin": "o", "mode": "m", "clean_sha256": "0" * 64,
                                                       "gold_spans": [], "query": "q"}])
    monkeypatch.setattr(svc, "pipeline", lambda: _Raising(exc))
    app = create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(), budget_config=budget_cfg())
    return TestClient(app, raise_server_exceptions=False)


def test_retrieval_header_error_is_422_with_message(tmp_path, monkeypatch):
    c = _retrieval_client(tmp_path, monkeypatch, HeaderMissingError("header_missing: chunk c1", setting_id="s", chunk_id="c1"))
    r = c.get(f"{FAM}/retrieval", params={"setting_id": "s", "item_id": "i1"})
    assert r.status_code == 422
    assert r.json() == {"error": {"code": "validation_failed", "message": "header_missing: chunk c1"}}


def test_retrieval_setting_not_available_is_422(tmp_path, monkeypatch):
    c = _retrieval_client(tmp_path, monkeypatch, SettingNotAvailable("x not available"))
    assert c.get(f"{FAM}/retrieval", params={"setting_id": "s", "item_id": "i1"}).status_code == 422


def test_retrieval_other_error_is_not_422(tmp_path, monkeypatch):
    c = _retrieval_client(tmp_path, monkeypatch, RuntimeError("boom"))
    assert c.get(f"{FAM}/retrieval", params={"setting_id": "s", "item_id": "i1"}).status_code == 500


@pytest.mark.parametrize("exc", [GridRunError("bad scope"), ConfigError("missing"), OSError("io"), ValueError("v"), KeyError("k"), TypeError("t")])
def test_header_binding_unreadable_config_means_none_and_is_logged(tmp_path, monkeypatch, caplog, exc):
    (tmp_path / "headers").mkdir()

    def boom(**kw):
        raise exc

    monkeypatch.setattr("backend.api.service.load_header_binding", boom)
    with caplog.at_level(logging.WARNING, logger="backend.api.service"):
        assert Service(runs_dir=tmp_path).header_binding() is None
    assert any("header B binding unavailable" in r.getMessage() and type(exc).__name__ in r.getMessage() for r in caplog.records)


def test_header_binding_unexpected_bug_is_not_swallowed(tmp_path, monkeypatch):
    (tmp_path / "headers").mkdir()

    def boom(**kw):
        raise RuntimeError("bug")

    monkeypatch.setattr("backend.api.service.load_header_binding", boom)
    with pytest.raises(RuntimeError):
        Service(runs_dir=tmp_path).header_binding()
