"""R4 `GET /api/families/{family}/docs/{doc_id}` (docs/API.md §2): teks bersih dan potongan satu setting."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from backend.api.errors import ApiError
from backend.api.service import FAMILIES

router = APIRouter()


def check_family(family: str) -> None:
    if family not in FAMILIES:
        raise ApiError(400, "invalid_request", f"family must be one of {list(FAMILIES)}.")


def header_rows(hb: Any, chunker: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """`headers` R4 untuk setting header-on: `[{chunk_id, header, tokens_local}]` (subset HeaderB DATA-CONTRACTS §7 yang dipakai UI),
    urut potongan, hanya potongan yang punya header di store (granularitas `expected_granularity`). Hanya membaca berkas; tanpa Spark."""
    if hb is None:
        return None
    gran = hb.expected_granularity(chunker)
    rows = []
    for c in chunks:
        rec = hb.store.get(c["chunk_id"], gran)
        if rec is not None and isinstance(rec.get("header"), str) and rec["header"].strip():
            rows.append({"chunk_id": c["chunk_id"], "header": rec["header"], "tokens_local": rec.get("tokens_local")})
    return rows


@router.get("/api/families")
def get_families(request: Request) -> list[dict[str, Any]]:
    """R2: `[{family, n_docs, n_items, has_grid}]`. Hanya membaca berkas (butir, hasil grid tersimpan); `n_items` dari
    `data/butir/<keluarga>.vN.jsonl` terbaru, 0 bila belum ada. `has_grid` = ada run grid tersimpan untuk kunci saat ini."""
    svc = request.app.state.service
    out = []
    for family in FAMILIES:
        try:  # galat satu keluarga (butir cacat, 409/422) tidak boleh menjatuhkan keluarga lain
            _plan, env = svc.stored_grid(family)
            row = {"family": family, "n_docs": len(svc.doc_ids(family)), "n_items": len(svc.items(family)), "has_grid": env is not None}
        except ApiError as exc:
            row = {"family": family, "n_docs": len(svc.doc_ids(family)), "n_items": 0, "has_grid": False, "error": exc.code}
        out.append(row)
    return out


@router.get("/api/families/{family}/docs/{doc_id}")
def get_doc(request: Request, family: str, doc_id: str, setting_id: str | None = None, schema_version: int | None = None) -> dict[str, Any]:
    """Tanpa `setting_id`/`schema_version`: `chunks = null`. Setting yang komponennya belum ada di M1: 422.
    `schema_version` (usulan API.md §2 R4): potongan menurut skema A tersimpan keluarga itu (read-only); versi tak ada: 404
    `not_found`; skema tak cocok dengan dokumen: 422. Bersama `setting_id`: 400 `invalid_request`."""
    svc = request.app.state.service
    check_family(family)
    doc = svc.doc(doc_id)
    if doc.family != family:
        raise ApiError(404, "not_found", f"Unknown doc_id {doc_id!r} for family {family!r}.")
    if setting_id is not None and schema_version is not None:
        raise ApiError(400, "invalid_request", "Pass either setting_id or schema_version, not both.")
    chunks = None
    headers = None
    if schema_version is not None:
        chunks = svc.schema_chunks(doc, schema_version)
    elif setting_id is not None:
        setting = svc.find_setting(family, setting_id)
        chunks = svc.chunks(doc, setting)
        if setting.header_b:
            headers = header_rows(svc.header_binding(family), setting.chunker, chunks)
    return {"doc_id": doc.doc_id, "text": doc.text, "chunks": chunks, "headers": headers}
