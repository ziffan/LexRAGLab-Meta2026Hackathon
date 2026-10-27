"""Uji API R4 dan snapshot sebagian (M1.1). Tanpa httpx (bukan dependensi): panggilan ASGI langsung.

Tanpa jaringan, tanpa Model API.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from backend import config
from backend.api import app as api_app
from backend.api.app import Service, create_app
from backend.tokenizer import get_tokenizer

from ._chunk_util import real_doc


def call(app, path: str, query: str = "") -> tuple[int, dict[str, Any]]:
    async def run() -> tuple[int, bytes]:
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
                 "headers": [(b"host", b"127.0.0.1")], "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8000)}
        sent: list[dict[str, Any]] = []
        done = False

        async def receive() -> dict[str, Any]:
            nonlocal done
            if not done:
                done = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        try:
            await app(scope, receive, send)
        except Exception:  # ServerErrorMiddleware mengirim respons 500 lalu melempar ulang; respons sudah ada
            pass
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return status, body

    status, body = asyncio.run(run())
    return status, json.loads(body)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    # runs_dir kosong: snapshot M1.1 tidak boleh bergantung pada run grid tersimpan di repo
    return create_app(Service(tokenizer=get_tokenizer(), runs_dir=tmp_path_factory.mktemp("runs")))


@pytest.fixture(scope="module")
def snap(app):
    st, body = call(app, "/api/families/uupt/snapshot")
    assert st == 200
    return body


def m11_settings(snap):
    """Dua setting M1.1: bm25, header B off, anggaran default (sekarang bagian dari grid penuh INT-a)."""
    return [s for s in snap["settings"] if s["chunker"] in ("structure_handwritten", "fixed_size") and s["retrieval_mode"] == "bm25"
            and not s["header_b"] and s["budget_tokens"] == snap["budget_tokens"]]


def setting(snap, chunker):
    return next(s for s in m11_settings(snap) if s["chunker"] == chunker)


def test_snapshot_exposes_items_and_the_two_m11_settings(snap):
    assert snap["family"] == "uupt" and snap["replay"] is False and snap["budget_tokens"] == 2000
    assert [i["id"] for i in snap["items"]][:2] == ["kontrol-K-01", "kontrol-K-02"] and len(snap["items"]) == 9
    assert [s["chunker"] for s in m11_settings(snap)] == ["structure_handwritten", "fixed_size"]
    assert len(snap["settings"]) == 36 and snap["split"] is None and snap["items_summary"]["by_split"] is None
    fx = config.load("grid")["fixed_size"]
    f = setting(snap, "fixed_size")
    assert (f["chunk_size_tokens"], f["overlap_tokens"]) == (fx["chunk_size_tokens"], fx["overlap_tokens"])
    assert len({s["setting_id"] for s in snap["settings"]}) == 36
    assert snap["corpus"][0]["clean_sha256"] == real_doc().clean_sha256 and "text" not in snap["corpus"][0]
    assert snap["grid"] is None and snap["metrics"] == [] and snap["items_summary"]["n_items"] == 9


def test_setting_id_is_hash_of_canonical_content(snap):
    from backend.chunking import make_setting_id
    for s in snap["settings"]:
        assert s["setting_id"] == make_setting_id({k: v for k, v in s.items() if k != "setting_id"})
        assert set(s) == {"setting_id", "family", "chunker", "chunk_size_tokens", "overlap_tokens", "schema_version", "retrieval_mode", "header_b", "budget_tokens"}


@pytest.mark.parametrize("chunker", ["structure_handwritten", "fixed_size"])
def test_r4_returns_text_and_chunks(app, snap, chunker):
    sid = setting(snap, chunker)["setting_id"]
    st, body = call(app, "/api/families/uupt/docs/uupt-40-2007", f"setting_id={sid}")
    assert st == 200 and set(body) == {"doc_id", "text", "chunks", "headers"}
    doc = real_doc()
    assert body["text"] == doc.text and body["headers"] is None
    assert len(body["chunks"]) > 50  # fixed_size berurutan lintas Pasal: 103 potongan (H-062)
    for c in body["chunks"]:
        assert c["clean_sha256"] == doc.clean_sha256
        assert 0 <= c["start"] < c["end"] <= len(body["text"])
        assert body["text"][c["start"]:c["end"]].strip()


def test_r4_pasal_86_addresses_come_through_the_api(app, snap):
    sid = setting(snap, "structure_handwritten")["setting_id"]
    _, body = call(app, "/api/families/uupt/docs/uupt-40-2007", f"setting_id={sid}")
    addrs = {c["address"] for c in body["chunks"]}
    assert "UU 40/2007 › Pasal 86 › ayat (9)" in addrs and "UU 40/2007 › Penjelasan › Pasal 86 › Ayat (9)" in addrs


def test_r4_without_setting_id_has_null_chunks(app):
    st, body = call(app, "/api/families/uupt/docs/uupt-40-2007")
    assert st == 200 and body["chunks"] is None and len(body["text"]) == real_doc().char_count


def assert_clean_error(st: int, body: dict[str, Any], status: int, code: str) -> None:
    assert st == status and set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code
    text = json.dumps(body)
    assert "Traceback" not in text and "File \"" not in text and ".py" not in text


def test_unknown_setting_id_is_404_without_stack_trace(app):
    st, body = call(app, "/api/families/uupt/docs/uupt-40-2007", "setting_id=" + "0" * 64)
    assert_clean_error(st, body, 404, "not_found")


def test_unknown_doc_family_and_route_errors(app):
    assert_clean_error(*call(app, "/api/families/uupt/docs/nope"), 404, "not_found")
    assert_clean_error(*call(app, "/api/families/akta/docs/uupt-40-2007"), 404, "not_found")
    assert_clean_error(*call(app, "/api/families/xyz/docs/uupt-40-2007"), 400, "invalid_request")
    assert_clean_error(*call(app, "/api/does-not-exist"), 404, "not_found")
    assert_clean_error(*call(app, "/api/families/uupt/snapshot", "budget_tokens=abc"), 400, "invalid_request")


def test_snapshot_rejects_items_written_against_other_clean_text(tmp_path: Path):
    shutil.copy(config.REPO_ROOT / "data" / "butir" / "uupt.v1.jsonl", tmp_path / "uupt.v1.jsonl")
    p = tmp_path / "uupt.v1.jsonl"
    p.write_bytes(p.read_bytes().replace(b"c56e4f0f38a4", b"000000000000", 1))
    a = create_app(Service(butir_dir=tmp_path))
    assert_clean_error(*call(a, "/api/families/uupt/snapshot"), 409, "hash_mismatch")


def test_chunk_offset_mismatch_is_an_error_not_a_warning(monkeypatch, snap):
    """Offset potongan yang tidak cocok dengan teks sumber = galat 422 (UI-SPEC U1)."""
    import dataclasses

    import backend.chunking as ch

    real = ch.chunk_structure

    def shifted(doc, **kw):
        cs = real(doc, **kw)
        return [dataclasses.replace(cs[0], start=cs[0].start + 3)] + cs[1:]

    monkeypatch.setattr(ch, "chunk_structure", shifted)
    a = create_app(Service(tokenizer=get_tokenizer()))
    sid = setting(snap, "structure_handwritten")["setting_id"]
    st, body = call(a, "/api/families/uupt/docs/uupt-40-2007", f"setting_id={sid}")
    assert_clean_error(st, body, 422, "validation_failed")
    assert "do not match" in body["error"]["message"]


def test_unexpected_exception_is_500_without_trace(monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("secret internal detail C:\\path\\x.py")

    monkeypatch.setattr(api_app.Service, "items", boom)
    a = create_app(Service())
    st, body = call(a, "/api/families/uupt/snapshot")
    assert_clean_error(st, body, 500, "internal_error")
    assert "secret" not in json.dumps(body)


def test_server_binds_localhost_only():
    import backend.api.__main__ as m
    assert m.HOST == "127.0.0.1"
