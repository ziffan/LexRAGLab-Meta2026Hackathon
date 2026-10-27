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


@router.get("/api/families/{family}/docs/{doc_id}")
def get_doc(request: Request, family: str, doc_id: str, setting_id: str | None = None) -> dict[str, Any]:
    """Tanpa `setting_id`: `chunks = null`. Setting yang komponennya belum ada di M1: 422."""
    svc = request.app.state.service
    check_family(family)
    if family != "uupt":
        raise ApiError(404, "not_found", f"Unknown doc_id {doc_id!r} for family {family!r}.")
    doc = svc.doc(doc_id)
    chunks = None
    if setting_id is not None:
        chunks = svc.chunks(doc, svc.find_setting(family, setting_id))
    return {"doc_id": doc.doc_id, "text": doc.text, "chunks": chunks, "headers": None}
