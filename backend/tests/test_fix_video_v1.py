"""Perbaikan video v1: F2 flag `--replay` pada `python -m backend.api`; F4 R4 `headers` dari store header nyata
(`runs/headers/`, read-only, tanpa Spark). Tanpa jaringan dan tanpa Model API."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from backend.api import __main__ as entry
from backend.api.app import Service, create_app
from backend.tokenizer import get_tokenizer

from .pipeline_fakes import FakeEncoder

DOC = "/api/families/uupt/docs/uupt-40-2007"


@pytest.mark.parametrize("argv,expected", [(["--replay"], True), ([], False)])
def test_main_replay_flag(monkeypatch, argv, expected):
    seen = {}
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: seen.update(app=app, kw=kw))
    monkeypatch.setattr(entry, "create_app", lambda **kw: create_app(Service(tokenizer=get_tokenizer(), encoder=FakeEncoder()), **{**kw, "warm_index": False}))
    monkeypatch.setattr(sys, "argv", ["backend.api", *argv])
    entry.main()
    assert seen["app"].state.replay is expected and seen["kw"]["host"] == "127.0.0.1"
    assert TestClient(seen["app"]).get("/api/health").headers["X-Replay"] == str(expected).lower()


@pytest.fixture(scope="module")
def svc():
    return Service(tokenizer=get_tokenizer(), encoder=FakeEncoder())  # runs/ nyata di repo (hanya dibaca)


def pick(svc, header):
    return next(s for s in svc.grid_settings("uupt") if s.chunker == "structure_handwritten" and s.header_b is header
                and s.retrieval_mode == "bm25" and s.budget_tokens == 2000)


def test_r4_headers_for_header_on_setting_match_chunks(svc):
    c = TestClient(create_app(svc))
    j = c.get(DOC, params={"setting_id": pick(svc, True).setting_id}).json()
    by_id = {h["chunk_id"]: h for h in j["headers"]}
    assert j["headers"] and set(by_id) <= {x["chunk_id"] for x in j["chunks"]}
    p102 = next(x for x in j["chunks"] if x["address"].endswith("Pasal 102") or "Pasal 102" in x["address"])
    h = by_id[p102["chunk_id"]]
    assert set(h) == {"chunk_id", "header", "tokens_local"} and h["header"].strip() and isinstance(h["tokens_local"], int)


def test_r4_headers_null_when_header_off_or_schema_version(svc):
    c = TestClient(create_app(svc))
    off = c.get(DOC, params={"setting_id": pick(svc, False).setting_id}).json()
    assert off["chunks"] and off["headers"] is None
    assert c.get(DOC).json()["headers"] is None
