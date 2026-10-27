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


@router.get("/api/families")
def get_families(request: Request) -> list[dict[str, Any]]:
    """R2: `[{family, n_docs, n_items, has_grid}]`. Hanya membaca berkas (butir, hasil grid tersimpan); `n_items` dari
    `data/butir/<keluarga>.vN.jsonl` terbaru, 0 bila belum ada. `has_grid` = ada run grid tersimpan untuk kunci saat ini."""
    svc = request.app.state.service
    out = []
    for family in FAMILIES:
        _plan, env = svc.stored_grid(family)
        out.append({"family": family, "n_docs": len(svc.doc_ids(family)), "n_items": len(svc.items(family)), "has_grid": env is not None})
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
    if schema_version is not None:
        chunks = svc.schema_chunks(doc, schema_version)
    elif setting_id is not None:
        chunks = svc.chunks(doc, svc.find_setting(family, setting_id))
    return {"doc_id": doc.doc_id, "text": doc.text, "chunks": chunks, "headers": None}
